# queries.py

Q_LIST_APPLICATIONS = """
MATCH (a:ApplicationRequirement)
RETURN a.applicationId AS applicationId, a.applicationType AS applicationType
ORDER BY applicationId;
"""

Q_GET_APPLICATION_DETAILS = """
MATCH (a:ApplicationRequirement {applicationId: $appId})
RETURN
  a.applicationId AS applicationId,
  a.applicationType AS applicationType,
  a.industrySector AS industrySector,

  a.payloadMinKg AS payloadMinKg,
  a.payloadMaxKg AS payloadMaxKg,
  a.reachMinMm AS reachMinMm,
  a.reachMaxMm AS reachMaxMm,
  a.repeatabilityRequiredMm AS repeatabilityRequiredMm,
  a.axesMin AS axesMin,

  a.budgetMinUsd AS budgetMinUsd,
  a.budgetMaxUsd AS budgetMaxUsd,
  a.cycleTimeTargetSec AS cycleTimeTargetSec,
  a.ipRatingMin AS ipRatingMin,

  a.cleanroomRequired AS cleanroomRequired,
  a.esdProtection AS esdProtection,
  a.forceSensingRequired AS forceSensingRequired,
  a.typicalRobotType AS typicalRobotType,
  a.speedPriority AS speedPriority,
  a.safetyClassification AS safetyClassification
LIMIT 1;
"""
Q_RANK_ROBOTS_FOR_APP = r"""
// ------------------------------------------------------------
// Purpose:
//   Rank all robots for a selected application by a weighted "distanceScore" (lower is better),
//   while optionally enforcing "hard constraints" (must-pass filters).
//
// Key design decisions (this version):
//   1) Payload & Reach suitability are MIN-only (overspec allowed):
//        - passPayload = robot.payload >= payloadMinR
//        - passReach   = robot.reach   >= reachMinR
//      Overspec is detected separately (payload/reach), and *also* for cleanroom ISO.
//      Scoring:
//        - inside [min,max] => gap = 0
//        - below min        => full penalty (underspec is bad)
//        - above max        => soft penalty scaled by wOverspec (acceptable but discouraged)
//
//      Hard constraint toggles for Payload/Reach still enforce FULL RANGE if enabled.
//
//   2) Budget handling is STRICT on "too expensive", and FLAG-ONLY on "too cheap":
//        - passBudget fails ONLY if robot is above app max (costMin > budgetMax)
//        - budgetTooCheap = TRUE if robot range entirely below app min (warning only)
//        - budgetGap penalises ONLY "too expensive"
//
//   3) Robot type match supports multi-token app types like "SCARA; Compact 6-axis".
//
//   4) Cleanroom supports mixed representations (ISO class vs yes/no/optional):
//        App cleanroomRequired:
//          - ISO N => require robot ISO <= N OR robot "yes" (unknown ISO) => PASS but needs-info
//          - yes/required (no ISO) => require robot has ISO or yes => PASS but needs-info (specify ISO)
//          - no/optional/blank => ignored
//
//        Robot cleanroomOption:
//          - ISO N => numeric capability
//          - yes/optional => 999 (capable but ISO unknown)
//          - no/blank => null
//
//      ESD/Force are treated as conditional yes/no/optional.
//      "optional" is treated as capable; "required/req" treated as true.
//
//   5) Relaxation sliders widen/narrow the requirement envelope before scoring.
//
// ------------------------------------------------------------

MATCH (a:ApplicationRequirement {applicationId: $appId})
MATCH (r:Robot)

// Bring in UI parameters (weights + relaxations + overspec penalty scalar)
WITH r, a,
     $relaxReachPct / 100.0     AS relaxReach,
     $relaxPayloadPct / 100.0   AS relaxPayload,
     $relaxPrecisionPct / 100.0 AS relaxPrecision,
     $wPayload   AS wPayload,
     $wReach     AS wReach,
     $wPrecision AS wPrecision,
     $wAxes      AS wAxes,
     $wOverspec  AS wOverspec

// Other weighted criteria (not relaxed, but still weighted)
WITH r, a, relaxReach, relaxPayload, relaxPrecision,
     wPayload, wReach, wPrecision, wAxes, wOverspec,
     $wBudget    AS wBudget,
     $wCycle     AS wCycle,
     $wIP        AS wIP,
     $wCleanroom AS wCleanroom,
     $wESD       AS wESD,
     $wForce     AS wForce,
     $wType      AS wType

// Apply "what-if" relaxation to build relaxed requirement envelope
WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     (a.payloadMinKg * (1 - relaxPayload))               AS payloadMinR,
     (a.payloadMaxKg * (1 + relaxPayload))               AS payloadMaxR,
     (a.reachMinMm   * (1 - relaxReach))                 AS reachMinR,
     (a.reachMaxMm   * (1 + relaxReach))                 AS reachMaxR,
     (a.repeatabilityRequiredMm * (1 + relaxPrecision))  AS repReqR,
     a.axesMin AS axesMinR

// ------------------------------------------------------------
// Cleanroom / ESD / Force parsing (mixed representations)
// ------------------------------------------------------------
WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,

     // raw strings
     toLower(trim(toString(coalesce(r.cleanroomOption, "")))) AS rCleanStr,
     toLower(trim(toString(coalesce(a.cleanroomRequired, "")))) AS aCleanStr,

     toLower(trim(toString(coalesce(r.esdSafe, ""))))         AS rEsdStr,
     toLower(trim(toString(coalesce(r.forceSensing, ""))))    AS rForceStr,
     toLower(trim(toString(coalesce(a.esdProtection, ""))))   AS aEsdStr,
     toLower(trim(toString(coalesce(a.forceSensingRequired, "")))) AS aForceStr

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     rCleanStr, aCleanStr, rEsdStr, rForceStr, aEsdStr, aForceStr,

     // App cleanroom requirement:
     //  - NULL/false/no/optional => null (not required)
     //  - ISO number present     => integer ISO requirement
     //  - yes/required           => 999 (required but ISO unspecified)
     CASE
       WHEN aCleanStr = "" OR aCleanStr IN ["false","no","n","0","none","na","n/a","-","optional","option"] THEN null
       WHEN aCleanStr =~ ".*[0-9].*" THEN
         toInteger(replace(replace(replace(replace(replace(aCleanStr,"iso",""),"class","")," ",""),"#",""),"grade",""))
       WHEN aCleanStr IN ["true","yes","y","1","required","req"] THEN 999
       ELSE 999
     END AS aCleanIsoReq,

     // Robot cleanroom capability:
     //  - ISO number present     => integer ISO capability
     //  - yes/true/optional      => 999 (capable but ISO unknown)
     //  - null/false/no          => null
     CASE
       WHEN rCleanStr = "" OR rCleanStr IN ["false","no","n","0","none","na","n/a","-"] THEN null
       WHEN rCleanStr =~ ".*[0-9].*" THEN
         toInteger(replace(replace(replace(replace(replace(rCleanStr,"iso",""),"class","")," ",""),"#",""),"grade",""))
       WHEN rCleanStr IN ["true","yes","y","1","optional","option","required","req"] THEN 999
       ELSE 999
     END AS rCleanIso,

     // ESD/Force truthiness (treat optional as capable; treat required/req as requiring)
     (rEsdStr   IN ["true","yes","y","1","optional","option","required","req"]) AS rEsdOK,
     (rForceStr IN ["true","yes","y","1","optional","option","required","req"]) AS rForceOK,
     (aEsdStr   IN ["true","yes","y","1","required","req"]) AS aEsdReq,
     (aForceStr IN ["true","yes","y","1","required","req"]) AS aForceReq

// ------------------------------------------------------------
// Parse costRangeUsd into numeric min/max (robust-ish parsing)
// ------------------------------------------------------------
WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     aCleanIsoReq, rCleanIso, rEsdOK, rForceOK, aEsdReq, aForceReq,
     toLower(replace(replace(replace(replace(toString(coalesce(r.costRangeUsd,"")), "–", "-"), "$",""), ",",""), " ", "")) AS costStr0

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     aCleanIsoReq, rCleanIso, rEsdOK, rForceOK, aEsdReq, aForceReq,
     replace(costStr0, "k", "000") AS costStr

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     aCleanIsoReq, rCleanIso, rEsdOK, rForceOK, aEsdReq, aForceReq,
     [x IN split(costStr, "-") | trim(x)] AS costParts

WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     aCleanIsoReq, rCleanIso, rEsdOK, rForceOK, aEsdReq, aForceReq,
     CASE WHEN size(costParts)=0 OR costParts[0]="" THEN null ELSE toFloat(costParts[0]) END AS costMin,
     CASE
       WHEN size(costParts) < 2 OR costParts[1] = "" THEN
         CASE WHEN size(costParts)=0 OR costParts[0]="" THEN null ELSE toFloat(costParts[0]) END
       ELSE toFloat(costParts[1])
     END AS costMax

// Flag "too cheap" (warning only): robot range entirely below app min
WITH r, a, wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     aCleanIsoReq, rCleanIso, rEsdOK, rForceOK, aEsdReq, aForceReq,
     costMin, costMax,
     CASE
       WHEN a.budgetMinUsd IS NULL OR costMax IS NULL THEN false
       ELSE (costMax < a.budgetMinUsd)
     END AS budgetTooCheap

// Parse IP ratings into numeric (IP67 -> 67). Missing becomes 0.
WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     aCleanIsoReq, rCleanIso, rEsdOK, rForceOK, aEsdReq, aForceReq,
     costMin, costMax, budgetTooCheap,
     toInteger(replace(toUpper(toString(coalesce(r.ipRating,"IP0"))), "IP", "")) AS ipRobot,
     toInteger(replace(toUpper(toString(coalesce(a.ipRatingMin,"IP0"))), "IP", "")) AS ipReq

// Bring in hard constraint toggles + compute per-criterion pass/fail + overspec flags
WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     aCleanIsoReq, rCleanIso, rEsdOK, rForceOK, aEsdReq, aForceReq,
     costMin, costMax, budgetTooCheap, ipRobot, ipReq,

     $hardPayload    AS hardPayload,
     $hardReach      AS hardReach,
     $hardPrecision  AS hardPrecision,
     $hardAxes       AS hardAxes,
     $hardBudget     AS hardBudget,
     $hardCycle      AS hardCycle,
     $hardIP         AS hardIP,
     $hardCleanroom  AS hardCleanroom,
     $hardESD        AS hardESD,
     $hardForce      AS hardForce,
     $hardType       AS hardType,

     // MIN-only pass: overspec allowed
     (r.payloadKg >= payloadMinR) AS passPayload,
     (r.reachMm   >= reachMinR)   AS passReach,

     // Overspec flags (only if max exists)
     CASE WHEN payloadMaxR IS NULL THEN false ELSE (r.payloadKg > payloadMaxR) END AS overspecPayload,
     CASE WHEN reachMaxR   IS NULL THEN false ELSE (r.reachMm   > reachMaxR)   END AS overspecReach,

     // upper bound pass: repeatability must be <=
     (r.repeatabilityMm <= repReqR) AS passPrecision,

     // lower bound pass: axis must be >=
     (r.axis >= axesMinR) AS passAxes,

     // Budget pass: fail ONLY if too expensive (costMin > budgetMax)
     CASE
       WHEN a.budgetMaxUsd IS NULL OR costMin IS NULL THEN true
       ELSE (costMin <= a.budgetMaxUsd)
     END AS passBudget,

     // cycle time (<=) if both exist
     CASE
       WHEN a.cycleTimeTargetSec IS NULL OR r.cycleTimeSec IS NULL THEN true
       ELSE (r.cycleTimeSec <= a.cycleTimeTargetSec)
     END AS passCycle,

     // --- Cleanroom ISO-aware pass ---
     // ISO required: accept robot ISO <= req OR robot "yes" (unknown ISO) => pass but needs-info
     CASE
       WHEN aCleanIsoReq IS NULL THEN true
       WHEN aCleanIsoReq = 999 THEN (rCleanIso IS NOT NULL)
       ELSE (
         rCleanIso IS NOT NULL AND (
           (rCleanIso <> 999 AND rCleanIso <= aCleanIsoReq)
           OR (rCleanIso = 999)
         )
       )
     END AS passCleanroom,

     // needs-info:
     //   - app required (no ISO) => ask to specify ISO requirement
     //   - app ISO specified but robot is "yes" (unknown ISO) => confirm with manufacturer
     CASE
       WHEN aCleanIsoReq IS NULL THEN false
       WHEN aCleanIsoReq = 999 THEN (rCleanIso IS NOT NULL)
       ELSE (rCleanIso = 999)
     END AS cleanroomNeedsInfo,

     // overspec cleanroom: only when both numeric ISO values known and robot is cleaner (lower)
     CASE
       WHEN aCleanIsoReq IS NULL OR aCleanIsoReq = 999 THEN false
       WHEN rCleanIso IS NULL OR rCleanIso = 999 THEN false
       ELSE (rCleanIso < aCleanIsoReq)
     END AS overspecCleanroom,

     // conditional boolean feature requirements
     CASE WHEN aEsdReq   THEN rEsdOK   ELSE true END AS passESD,
     CASE WHEN aForceReq THEN rForceOK ELSE true END AS passForce,

     // IP: if app has min IP, robot must be >=
     CASE
       WHEN a.ipRatingMin IS NULL THEN true
       ELSE (ipRobot >= ipReq)
     END AS passIP,

     // Robot type match: app tokens may include multiple acceptable bases
     CASE
       WHEN a.typicalRobotType IS NULL OR trim(toString(a.typicalRobotType)) = "" THEN true
       ELSE
         any(reqBase IN
           [tok IN split(
               replace(replace(replace(toLower(toString(a.typicalRobotType)),"/", ";"), ",", ";"), "  ", " "),
               ";"
            ) |
            CASE
              WHEN trim(tok) = "" THEN ""
              WHEN tok CONTAINS "scara" THEN "scara"
              WHEN tok CONTAINS "6-axis" OR tok CONTAINS "6 axis" OR tok CONTAINS "6axis" THEN "6-axis"
              WHEN tok CONTAINS "cobot" THEN "cobot"
              ELSE trim(tok)
            END
           ]
           WHERE reqBase <> "" AND reqBase = toLower(trim(toString(r.type)))
         )
     END AS passType

// Apply hard constraints as filters
// NOTE: for Payload/Reach hard constraints, enforce FULL RANGE.
WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, budgetTooCheap, ipRobot, ipReq,
     passPayload, passReach, overspecPayload, overspecReach, passPrecision, passAxes,
     passBudget, passCycle,
     passCleanroom, cleanroomNeedsInfo, overspecCleanroom,
     passESD, passForce, passIP, passType,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     aCleanIsoReq, rCleanIso, aEsdReq, aForceReq, rEsdOK, rForceOK,
     hardPayload, hardReach, hardPrecision, hardAxes,
     hardBudget, hardCycle, hardIP,
     hardCleanroom, hardESD, hardForce,
     hardType

WHERE
    (
      NOT hardPayload
      OR (r.payloadKg >= payloadMinR AND (payloadMaxR IS NULL OR r.payloadKg <= payloadMaxR))
    )
AND (
      NOT hardReach
      OR (r.reachMm >= reachMinR AND (reachMaxR IS NULL OR r.reachMm <= reachMaxR))
    )
AND (NOT hardPrecision OR passPrecision)
AND (NOT hardAxes      OR passAxes)
AND (NOT hardBudget    OR passBudget)
AND (NOT hardCycle     OR passCycle)
AND (NOT hardIP        OR passIP)
AND (NOT hardCleanroom OR passCleanroom)
AND (NOT hardESD       OR passESD)
AND (NOT hardForce     OR passForce)
AND (NOT hardType      OR passType)

// Compute gaps:
//  - inside range => 0
//  - underspec    => full penalty
//  - overspec     => soft penalty scaled by wOverspec
WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, budgetTooCheap, ipRobot, ipReq,
     passPayload, passReach, overspecPayload, overspecReach, passPrecision, passAxes,
     passBudget, passCycle,
     passCleanroom, cleanroomNeedsInfo, overspecCleanroom,
     passESD, passForce, passIP, passType,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType, wOverspec,
     aCleanIsoReq, rCleanIso,

     CASE
       WHEN r.payloadKg < payloadMinR THEN (payloadMinR - r.payloadKg) / payloadMinR
       WHEN payloadMaxR IS NULL OR r.payloadKg <= payloadMaxR THEN 0
       WHEN payloadMaxR = 0 THEN 0
       ELSE wOverspec * ((r.payloadKg - payloadMaxR) / payloadMaxR)
     END AS payloadGap,

     CASE
       WHEN r.reachMm < reachMinR THEN (reachMinR - r.reachMm) / reachMinR
       WHEN reachMaxR IS NULL OR r.reachMm <= reachMaxR THEN 0
       WHEN reachMaxR = 0 THEN 0
       ELSE wOverspec * ((r.reachMm - reachMaxR) / reachMaxR)
     END AS reachGap,

     CASE
       WHEN r.repeatabilityMm > repReqR THEN (r.repeatabilityMm - repReqR) / repReqR
       ELSE 0
     END AS precisionGap,

     CASE
       WHEN r.axis < axesMinR THEN (axesMinR - r.axis) * 1.0 / axesMinR
       ELSE 0
     END AS axesGap,

     CASE
       WHEN a.budgetMaxUsd IS NULL OR costMin IS NULL THEN 0
       WHEN costMin > a.budgetMaxUsd THEN (costMin - a.budgetMaxUsd) / a.budgetMaxUsd
       ELSE 0
     END AS budgetGap,

     CASE
       WHEN a.cycleTimeTargetSec IS NULL OR r.cycleTimeSec IS NULL THEN 0
       WHEN r.cycleTimeSec > a.cycleTimeTargetSec THEN (r.cycleTimeSec - a.cycleTimeTargetSec) / a.cycleTimeTargetSec
       ELSE 0
     END AS cycleGap,

     // Cleanroom gap:
     //  - pass => 0
     //  - overspec (cleaner than required) => soft penalty scaled by wOverspec
     //  - needs-info => moderate penalty (keeps in shortlist but lower rank)
     //  - fail => 1
     CASE
       WHEN aCleanIsoReq IS NULL THEN 0
       WHEN passCleanroom AND overspecCleanroom AND aCleanIsoReq > 0 THEN
         wOverspec * ((aCleanIsoReq - rCleanIso) * 1.0 / aCleanIsoReq)
       WHEN passCleanroom THEN 0
       WHEN cleanroomNeedsInfo THEN 0.35
       ELSE 1
     END AS cleanroomGap,

     CASE WHEN passESD   THEN 0 ELSE 1 END AS esdGap,
     CASE WHEN passForce THEN 0 ELSE 1 END AS forceGap,

     CASE
       WHEN a.ipRatingMin IS NULL THEN 0
       WHEN ipRobot < ipReq AND ipReq > 0 THEN (ipReq - ipRobot) * 1.0 / ipReq
       ELSE 0
     END AS ipGap,

     CASE WHEN passType THEN 0 ELSE 1 END AS typeGap

// Weighted total score + suitability labels
WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, budgetTooCheap, ipRobot, ipReq,
     passPayload, passReach, overspecPayload, overspecReach, passPrecision, passAxes,
     passBudget, passCycle,
     passCleanroom, cleanroomNeedsInfo, overspecCleanroom,
     passESD, passForce, passIP, passType,
     payloadGap, reachGap, precisionGap, axesGap,
     budgetGap, cycleGap, ipGap, cleanroomGap, esdGap, forceGap, typeGap,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     aCleanIsoReq, rCleanIso,
     (wPayload+wReach+wPrecision+wAxes+wBudget+wCycle+wIP+wCleanroom+wESD+wForce+wType) AS wTotal

WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, budgetTooCheap, ipRobot, ipReq,
     passPayload, passReach, overspecPayload, overspecReach, passPrecision, passAxes,
     passBudget, passCycle,
     passCleanroom, cleanroomNeedsInfo, overspecCleanroom,
     passESD, passForce, passIP, passType,
     payloadGap, reachGap, precisionGap, axesGap,
     budgetGap, cycleGap, ipGap, cleanroomGap, esdGap, forceGap, typeGap,
     wPayload, wReach, wPrecision, wAxes,
     wBudget, wCycle, wIP, wCleanroom, wESD, wForce, wType,
     aCleanIsoReq, rCleanIso, wTotal,

     (
       wPayload*payloadGap +
       wReach*reachGap +
       wPrecision*precisionGap +
       wAxes*axesGap +
       wBudget*budgetGap +
       wCycle*cycleGap +
       wIP*ipGap +
       wCleanroom*cleanroomGap +
       wESD*esdGap +
       wForce*forceGap +
       wType*typeGap
     ) / CASE WHEN wTotal = 0 THEN 1 ELSE wTotal END AS distanceScoreRaw,

     // Base suitability (passes all "pass*" checks, may still be overspecced)
     (
       passPayload AND passReach AND passPrecision AND passAxes AND
       passBudget AND passCycle AND passCleanroom AND passESD AND passForce AND passIP AND passType
     ) AS baseSuitable,

     // Suitable but overspecced = baseSuitable + overspec flags
     (
       (passPayload AND passReach AND passPrecision AND passAxes AND
        passBudget AND passCycle AND passCleanroom AND passESD AND passForce AND passIP AND passType)
       AND (overspecPayload OR overspecReach OR overspecCleanroom)
     ) AS suitableButOverspecced,

     [
       CASE WHEN NOT passPayload    THEN "Payload below minimum" END,
       CASE WHEN NOT passReach      THEN "Reach below minimum" END,
       CASE WHEN NOT passPrecision  THEN "Repeatability not sufficient" END,
       CASE WHEN NOT passAxes       THEN "Insufficient axes" END,
       CASE WHEN NOT passBudget     THEN "Budget too high" END,
       CASE WHEN budgetTooCheap     THEN "Budget unusually low (verify quality/hidden costs)" END,
       CASE WHEN NOT passCycle      THEN "Cycle time too slow" END,
       CASE WHEN NOT passIP         THEN "IP rating too low" END,

       CASE
         WHEN aCleanIsoReq IS NULL THEN null
         WHEN passCleanroom AND overspecCleanroom THEN "Cleanroom overspecced (cleaner than required)"
         WHEN passCleanroom AND cleanroomNeedsInfo AND aCleanIsoReq = 999 THEN "Cleanroom required but ISO class not specified (specify ISO requirement)"
         WHEN passCleanroom AND cleanroomNeedsInfo AND aCleanIsoReq <> 999 THEN "Robot cleanroom ISO class unknown (confirm with manufacturer)"
         WHEN passCleanroom THEN null
         ELSE "Cleanroom requirement not met"
       END,

       CASE WHEN NOT passESD   THEN "ESD protection required" END,
       CASE WHEN NOT passForce THEN "Force sensing required" END,
       CASE WHEN NOT passType  THEN "Robot type mismatch" END
     ] AS rawReasons

WITH r, a,
     payloadMinR, payloadMaxR, reachMinR, reachMaxR, repReqR, axesMinR,
     costMin, costMax, budgetTooCheap, ipRobot, ipReq,
     baseSuitable, suitableButOverspecced, distanceScoreRaw,
     overspecPayload, overspecReach, overspecCleanroom,
     cleanroomNeedsInfo, aCleanIsoReq, rCleanIso,
     [x IN rawReasons WHERE x IS NOT NULL] AS reasons,

     // fullySuitable is exclusive: suitable AND NOT overspecced
     (baseSuitable AND NOT (overspecPayload OR overspecReach OR overspecCleanroom)) AS fullySuitable,

     // overspec label string
     reduce(s="", x IN [y IN [
       CASE WHEN overspecPayload   THEN "payload" END,
       CASE WHEN overspecReach     THEN "reach" END,
       CASE WHEN overspecCleanroom THEN "cleanroom" END
     ] WHERE y IS NOT NULL] |
       CASE WHEN s="" THEN x ELSE s + ", " + x END
     ) AS overspecWhat

RETURN
  a.applicationId   AS appId,
  a.applicationType AS applicationType,

  r.robotModel      AS robot,
  r.type            AS robotType,
  r.manufacturer    AS manufacturer,

  fullySuitable,
  suitableButOverspecced,

  r.payloadKg         AS payloadKg,
  r.reachMm           AS reachMm,
  r.repeatabilityMm   AS repeatabilityMm,
  r.axis              AS axis,
  r.cycleTimeSec      AS cycleTimeSec,

  costMin             AS costMin,
  costMax             AS costMax,
  budgetTooCheap      AS budgetTooCheap,

  overspecPayload     AS overspecPayload,
  overspecReach       AS overspecReach,
  overspecCleanroom   AS overspecCleanroom,
  cleanroomNeedsInfo  AS cleanroomNeedsInfo,

  r.cleanroomOption   AS cleanroomOptionRaw,
  r.esdSafe           AS esdSafeRaw,
  r.forceSensing      AS forceSensingRaw,

  ipRobot             AS ipRatingNum,
  r.type              AS robotTypeRaw,

  payloadMinR          AS reqPayloadMinKg,
  payloadMaxR          AS reqPayloadMaxKg,
  reachMinR            AS reqReachMinMm,
  reachMaxR            AS reqReachMaxMm,
  repReqR              AS reqRepeatabilityMaxMm,
  axesMinR             AS reqAxesMin,

  a.budgetMinUsd       AS reqBudgetMinUsd,
  a.budgetMaxUsd       AS reqBudgetMaxUsd,
  a.cycleTimeTargetSec AS reqCycleTimeMaxSec,
  ipReq                AS reqIpRatingNum,

  a.cleanroomRequired  AS reqCleanroom,
  a.esdProtection      AS reqEsd,
  a.forceSensingRequired AS reqForceSensing,
  a.typicalRobotType   AS reqRobotType,

  // Parsed cleanroom debug fields (useful for UI/tooltips)
  aCleanIsoReq         AS reqCleanroomIsoParsed,
  rCleanIso            AS robotCleanroomIsoParsed,

  // ------------------------------------------------------------
  // Formatted strings for UI table/cards
  // ------------------------------------------------------------
  toString(r.payloadKg) + " kg (req " +
    toString(round(payloadMinR*100)/100.0) + "–" +
    toString(round(payloadMaxR*100)/100.0) + " kg)" AS payload,

  toString(r.reachMm) + " mm (req " +
    toString(round(reachMinR)) + "–" +
    toString(round(reachMaxR)) + " mm)" AS reach,

  toString(r.repeatabilityMm) + " mm (req ≤ " +
    toString(round(repReqR*1000)/1000.0) + " mm)" AS precision,

  toString(r.axis) + " (req ≥ " + toString(axesMinR) + ")" AS axes,

  CASE
    WHEN costMin IS NULL OR costMax IS NULL OR a.budgetMinUsd IS NULL OR a.budgetMaxUsd IS NULL THEN "—"
    ELSE toString(round(costMin)) + "–" + toString(round(costMax)) +
         " USD (req " + toString(a.budgetMinUsd) + "–" + toString(a.budgetMaxUsd) + " USD)"
  END AS budget,

  CASE
    WHEN r.cycleTimeSec IS NULL OR a.cycleTimeTargetSec IS NULL THEN "—"
    ELSE toString(r.cycleTimeSec) + " s (req ≤ " + toString(a.cycleTimeTargetSec) + " s)"
  END AS cycleTime,

  CASE
    WHEN a.ipRatingMin IS NULL OR ipReq IS NULL OR ipRobot IS NULL THEN "—"
    ELSE "IP" + toString(ipRobot) + " (req ≥ IP" + toString(ipReq) + ")"
  END AS ipRating,

  CASE
    WHEN a.cleanroomRequired IS NULL THEN "—"
    ELSE toString(r.cleanroomOption) + " (req " + toString(a.cleanroomRequired) + ")"
  END AS cleanroom,

  CASE
    WHEN a.esdProtection IS NULL THEN "—"
    ELSE toString(r.esdSafe) + " (req " + toString(a.esdProtection) + ")"
  END AS esd,

  CASE
    WHEN a.forceSensingRequired IS NULL THEN "—"
    ELSE toString(r.forceSensing) + " (req " + toString(a.forceSensingRequired) + ")"
  END AS forceSensing,

  CASE
    WHEN a.typicalRobotType IS NULL OR trim(toString(a.typicalRobotType)) = "" THEN "—"
    ELSE toString(r.type) + " (req " + toString(a.typicalRobotType) + ")"
  END AS robotTypeMatch,

  // Extra robot-only display fields
  CASE WHEN r.weightKg IS NULL THEN "—" ELSE toString(r.weightKg) + " kg" END AS weight,
  CASE WHEN r.mounting IS NULL OR trim(toString(r.mounting)) = "" THEN "—" ELSE toString(r.mounting) END AS mounting,
  CASE WHEN r.speedGrade IS NULL OR trim(toString(r.speedGrade)) = "" THEN "—" ELSE toString(r.speedGrade) END AS speedGrade,
  CASE WHEN r.applicationSuitability IS NULL OR trim(toString(r.applicationSuitability)) = "" THEN "—" ELSE toString(r.applicationSuitability) END AS applicationSuitability,
  CASE WHEN r.safetyFeature IS NULL OR trim(toString(r.safetyFeature)) = "" THEN "—" ELSE toString(r.safetyFeature) END AS safetyFeature,
  CASE WHEN r.programmingComplexity IS NULL OR trim(toString(r.programmingComplexity)) = "" THEN "—" ELSE toString(r.programmingComplexity) END AS programmingComplexity,

  // "special features" (supports either specialFeatures or special_features)
  CASE
    WHEN coalesce(r.specialFeatures, r.special_features) IS NULL OR trim(toString(coalesce(r.specialFeatures, r.special_features))) = "" THEN "—"
    ELSE toString(coalesce(r.specialFeatures, r.special_features))
  END AS specialFeatures,

  // Optional: robot name field if you want it
  CASE WHEN r.name IS NULL OR trim(toString(r.name)) = "" THEN "—" ELSE toString(r.name) END AS name,

  CASE
    WHEN suitableButOverspecced THEN "Meets all requirements (overspec: " + overspecWhat + ")"
    WHEN fullySuitable          THEN "Meets all requirements"
    ELSE reduce(s="", rr IN reasons | CASE WHEN s="" THEN rr ELSE s + "; " + rr END)
  END AS notes,

  round(distanceScoreRaw*10000)/10000 AS distanceScore,

  CASE
    WHEN distanceScoreRaw <= 0 THEN 100.0
    WHEN distanceScoreRaw >= 1 THEN 0.0
    ELSE (1 - distanceScoreRaw) * 100.0
  END AS fitScoreRaw

ORDER BY fullySuitable DESC, suitableButOverspecced DESC, distanceScoreRaw ASC, robot
LIMIT $limit;
"""