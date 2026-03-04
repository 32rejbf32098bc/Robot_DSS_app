// Robots suitable for S01, showing robot values next to application requirement ranges.

MATCH (a:ApplicationRequirement {applicationId:"S05"})
MATCH (r:Robot)

WITH
  a, r,
  (r.payloadKg - a.payloadMinKg) AS payloadMarginKg,
  (a.payloadMaxKg - r.payloadKg) AS payloadMaxMarginKg,
  (r.reachMm - a.reachMinMm) AS reachMarginMm,
  (a.reachMaxMm - r.reachMm) AS reachMaxMarginMm,
  (a.repeatabilityRequiredMm - r.repeatabilityMm) AS precisionMarginMm,
  (r.axis - a.axesMin) AS axesMargin

WHERE
  payloadMarginKg >= 0 AND payloadMaxMarginKg >= 0 AND
  reachMarginMm >= 0 AND reachMaxMarginMm >= 0 AND
  precisionMarginMm >= 0 AND
  axesMargin >= 0

RETURN
  r.robotModel AS robot,
  r.type AS robotType,

  // Show robot values next to requirement ranges
  r.payloadKg AS robotPayloadKg,
  (toString(a.payloadMinKg) + "–" + toString(a.payloadMaxKg)) AS requiredPayloadKgRange,

  r.reachMm AS robotReachMm,
  (toString(a.reachMinMm) + "–" + toString(a.reachMaxMm)) AS requiredReachMmRange,

  r.repeatabilityMm AS robotRepeatabilityMm,
  ("≤ " + toString(a.repeatabilityRequiredMm)) AS requiredRepeatabilityMm,

  r.axis AS robotAxes,
  (">= " + toString(a.axesMin)) AS requiredAxesMin,

  // Optional: why suitable (margins)
  payloadMarginKg,
  reachMarginMm,
  precisionMarginMm,
  axesMargin

ORDER BY precisionMarginMm DESC, payloadMarginKg DESC, reachMarginMm DESC;
//

MATCH (a:ApplicationRequirement {applicationId:"S05"})
MATCH (r:Robot)-[:SUITABLE_FOR]->(a)
RETURN
r.robotModel,
r.type,
r.reachMm,
a.reachMinMm,
a.reachMaxMm,
r.payloadKg,
a.payloadMinKg,
a.payloadMaxKg,
r.repeatabilityMm,
a.repeatabilityRequiredMm;

//
MATCH (r:Robot)-[rel:SUITABLE_FOR]->(a:ApplicationRequirement)
WHERE a.applicationId IN ["S01","S02","S03","S04","S05","S06","S07","S08","S09","S10"]
RETURN r, rel, a
LIMIT 200;

//
MATCH (r:Robot)-[rel]->(a:ApplicationRequirement {applicationId:"S01"})
WHERE type(rel) IN ["MEETS_PAYLOAD","MEETS_REACH","MEETS_PRECISION","MEETS_AXES","FULLY_SUITABLE_FOR"]
  RETURN r, rel, a
LIMIT 200;

//
MATCH (r:Robot)
MATCH (a:ApplicationRequirement {applicationId:"S01"})

WHERE
(r)-[:MEETS_PAYLOAD]->(a) AND
(r)-[:MEETS_REACH]->(a) AND
(r)-[:MEETS_PRECISION]->(a) AND
(r)-[:MEETS_AXES]->(a)

RETURN r.robotModel, r.type;
//

MATCH (a:ApplicationRequirement {applicationId:"S06"})
MATCH (r:Robot)-[:FULLY_SUITABLE_FOR]->(a)

WITH r, a,
  // Normalised-ish scores (higher is better)
  // You can tune weights based on the application’s priorities.
  (1.0 / r.repeatabilityMm)              AS precisionScore,
  (r.payloadKg / a.payloadMaxKg)         AS payloadScore,
  (r.reachMm / a.reachMaxMm)             AS reachScore,
  (r.axis - a.axesMin)                   AS extraAxesScore

WITH r, a,
  0.45*precisionScore +
  0.25*payloadScore +
  0.20*reachScore +
  0.10*extraAxesScore AS totalScore

RETURN
  r.robotModel        AS robot,
  r.type              AS robotType,
  r.payloadKg         AS payloadKg,
  r.reachMm           AS reachMm,
  r.repeatabilityMm   AS repeatabilityMm,
  r.axis              AS axes,
  round(totalScore*1000)/1000 AS score

ORDER BY score DESC
LIMIT 20;

//

MATCH (a:ApplicationRequirement {applicationId:"S01"})
MATCH (r:Robot)

WITH r, a,
  // constraint pass flags
  (r.payloadKg >= a.payloadMinKg AND r.payloadKg <= a.payloadMaxKg) AS passPayload,
  (r.reachMm   >= a.reachMinMm   AND r.reachMm   <= a.reachMaxMm)   AS passReach,
  (r.repeatabilityMm <= a.repeatabilityRequiredMm)                  AS passPrecision,
  (r.axis >= a.axesMin)                                             AS passAxes

WITH r, a, passPayload, passReach, passPrecision, passAxes,
  // penalty points (0 = ok, negative = bad)
  CASE WHEN passPayload THEN 0 ELSE -50 END AS pPayload,
  CASE WHEN passReach THEN 0 ELSE -40 END   AS pReach,
  CASE WHEN passPrecision THEN 0 ELSE -60 END AS pPrecision,
  CASE WHEN passAxes THEN 0 ELSE -30 END    AS pAxes

WITH r, a, passPayload, passReach, passPrecision, passAxes,
  (pPayload + pReach + pPrecision + pAxes) AS penalty,
  // base “quality” score (only meaningful when passing, but still helps ranking)
  (0.6*(1.0 / r.repeatabilityMm) + 0.2*(r.payloadKg / a.payloadMaxKg) + 0.2*(r.reachMm / a.reachMaxMm)) AS baseScore

WITH r, a, penalty, baseScore,
  (baseScore*100 + penalty) AS totalScore,
  [x IN [
    CASE WHEN passPayload    THEN null ELSE "Payload fail" END,
    CASE WHEN passReach      THEN null ELSE "Reach fail" END,
    CASE WHEN passPrecision  THEN null ELSE "Precision fail" END,
    CASE WHEN passAxes       THEN null ELSE "Axes fail" END
  ] WHERE x IS NOT NULL] AS fails

RETURN
  r.robotModel AS robot,
  r.type AS robotType,
  round(totalScore*1000)/1000 AS score,
  penalty,
  fails,
  r.payloadKg AS payload, a.payloadMinKg AS minPayload, a.payloadMaxKg AS maxPayload,
  r.reachMm AS reach, a.reachMinMm AS minReach, a.reachMaxMm AS maxReach,
  r.repeatabilityMm AS rep, a.repeatabilityRequiredMm AS repReq,
  r.axis AS axes, a.axesMin AS axesMin

ORDER BY score DESC
LIMIT 30;

//

MATCH (a:ApplicationRequirement {applicationId:"S01"})
MATCH (r:Robot)-[:FULLY_SUITABLE_FOR]->(a)
RETURN r.robotModel AS robot, r.type AS type, r.repeatabilityMm AS repeatability
ORDER BY repeatability ASC
LIMIT 10;

//

MATCH (a:ApplicationRequirement {applicationId:"S01"})
MATCH (r:Robot)

WITH r, a,
  // pass/fail flags
  (r.payloadKg >= a.payloadMinKg AND r.payloadKg <= a.payloadMaxKg) AS passPayload,
  (r.reachMm   >= a.reachMinMm   AND r.reachMm   <= a.reachMaxMm)   AS passReach,
  (r.repeatabilityMm <= a.repeatabilityRequiredMm)                  AS passPrecision,
  (r.axis >= a.axesMin)                                             AS passAxes,

  // gaps (0 means meets requirement)
  CASE
    WHEN r.payloadKg < a.payloadMinKg THEN (a.payloadMinKg - r.payloadKg) / a.payloadMinKg
    WHEN r.payloadKg > a.payloadMaxKg THEN (r.payloadKg - a.payloadMaxKg) / a.payloadMaxKg
    ELSE 0
  END AS payloadGap,

  CASE
    WHEN r.reachMm < a.reachMinMm THEN (a.reachMinMm - r.reachMm) / a.reachMinMm
    WHEN r.reachMm > a.reachMaxMm THEN (r.reachMm - a.reachMaxMm) / a.reachMaxMm
    ELSE 0
  END AS reachGap,

  CASE
    WHEN r.repeatabilityMm > a.repeatabilityRequiredMm
    THEN (r.repeatabilityMm - a.repeatabilityRequiredMm) / a.repeatabilityRequiredMm
    ELSE 0
  END AS precisionGap,

  CASE
    WHEN r.axis < a.axesMin THEN (a.axesMin - r.axis) * 1.0 / a.axesMin
    ELSE 0
  END AS axesGap

WITH r, a, passPayload, passReach, passPrecision, passAxes,
     payloadGap, reachGap, precisionGap, axesGap,
     (0.30*payloadGap + 0.25*reachGap + 0.35*precisionGap + 0.10*axesGap) AS distanceScore,
     (passPayload AND passReach AND passPrecision AND passAxes) AS fullySuitable

RETURN
  a.applicationId AS app,
  r.robotModel AS robot,
  r.type AS robotType,
  fullySuitable,

  // formatted columns for the report
  toString(round(r.payloadKg*100)/100.0) + " kg (req " +
    toString(a.payloadMinKg) + "–" + toString(a.payloadMaxKg) + ")" AS payload,

  toString(round(r.reachMm*1.0)/1.0) + " mm (req " +
    toString(a.reachMinMm) + "–" + toString(a.reachMaxMm) + ")" AS reach,

  toString(round(r.repeatabilityMm*1000)/1000.0) + " mm (req ≤ " +
    toString(a.repeatabilityRequiredMm) + ")" AS repeatability,

  toString(r.axis) + " (req ≥ " + toString(a.axesMin) + ")" AS axes,

  // single score for ranking
  round(distanceScore*1000)/1000 AS distanceScore

ORDER BY fullySuitable DESC, distanceScore ASC, robot
LIMIT 50;

//

MATCH (a:ApplicationRequirement {applicationId:"S01"})
MATCH (r:Robot)

WITH r, a,

// pass/fail checks
(r.payloadKg >= a.payloadMinKg AND r.payloadKg <= a.payloadMaxKg) AS passPayload,
(r.reachMm   >= a.reachMinMm   AND r.reachMm   <= a.reachMaxMm)   AS passReach,
(r.repeatabilityMm <= a.repeatabilityRequiredMm)                  AS passPrecision,
(r.axis >= a.axesMin)                                             AS passAxes,

// gap calculations
CASE
  WHEN r.payloadKg < a.payloadMinKg THEN (a.payloadMinKg - r.payloadKg) / a.payloadMinKg
  WHEN r.payloadKg > a.payloadMaxKg THEN (r.payloadKg - a.payloadMaxKg) / a.payloadMaxKg
  ELSE 0
END AS payloadGap,

CASE
  WHEN r.reachMm < a.reachMinMm THEN (a.reachMinMm - r.reachMm) / a.reachMinMm
  WHEN r.reachMm > a.reachMaxMm THEN (r.reachMm - a.reachMaxMm) / a.reachMaxMm
  ELSE 0
END AS reachGap,

CASE
  WHEN r.repeatabilityMm > a.repeatabilityRequiredMm
  THEN (r.repeatabilityMm - a.repeatabilityRequiredMm) / a.repeatabilityRequiredMm
  ELSE 0
END AS precisionGap,

CASE
  WHEN r.axis < a.axesMin THEN (a.axesMin - r.axis) * 1.0 / a.axesMin
  ELSE 0
END AS axesGap


WITH r, a, passPayload, passReach, passPrecision, passAxes,
     payloadGap, reachGap, precisionGap, axesGap,

// final weighted score
(0.30*payloadGap +
 0.25*reachGap +
 0.35*precisionGap +
 0.10*axesGap) AS distanceScore,


(passPayload AND passReach AND passPrecision AND passAxes) AS fullySuitable,

[
 CASE WHEN NOT passPayload THEN "Payload out of range" END,
 CASE WHEN NOT passReach THEN "Reach out of range" END,
 CASE WHEN NOT passPrecision THEN "Repeatability not sufficient" END,
 CASE WHEN NOT passAxes THEN "Insufficient axes" END
] AS rawReasons


WITH r, a, fullySuitable, distanceScore,
[x IN rawReasons WHERE x IS NOT NULL] AS reasons


RETURN

a.applicationId AS app,

r.robotModel AS robot,

r.type AS robotType,

fullySuitable,


// formatted requirement comparisons

toString(r.payloadKg) + " kg (req " +
toString(a.payloadMinKg) + "–" +
toString(a.payloadMaxKg) + ")" AS payload,


toString(r.reachMm) + " mm (req " +
toString(a.reachMinMm) + "–" +
toString(a.reachMaxMm) + ")" AS reach,


toString(r.repeatabilityMm) + " mm (req ≤ " +
toString(a.repeatabilityRequiredMm) + ")" AS repeatability,


toString(r.axis) + " (req ≥ " +
toString(a.axesMin) + ")" AS axes,


// reason column

CASE
WHEN fullySuitable
THEN "Meets all requirements"
ELSE reduce(s="", r IN reasons |
CASE WHEN s="" THEN r ELSE s + "; " + r END)
END AS notes,


round(distanceScore*1000)/1000 AS distanceScore


ORDER BY

distanceScore ASC,   // PRIMARY sort
fullySuitable DESC,  // secondary
robot;