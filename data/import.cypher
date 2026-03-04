// ---------------------------------------
// Optional: wipe data (ONLY if you want)
// ---------------------------------------
// MATCH (n) DETACH DELETE n;

// ---------------------------------------
// Constraints (recommended)
// ---------------------------------------
CREATE CONSTRAINT robot_model_unique IF NOT EXISTS
FOR (r:Robot) REQUIRE r.robotModel IS UNIQUE;

CREATE CONSTRAINT app_id_unique IF NOT EXISTS
FOR (a:ApplicationRequirement) REQUIRE a.applicationId IS UNIQUE;


// ---------------------------------------
// Helper pattern: import one robot CSV
// (repeat for each file)
// ---------------------------------------

LOAD CSV WITH HEADERS FROM "file:///HEAVY_DUTY_ROBOTS.csv" AS row
WITH row WHERE row.Robot_Model IS NOT NULL AND trim(row.Robot_Model) <> ""
MERGE (r:Robot {robotModel: trim(row.Robot_Model)})
SET
  r.manufacturer = trim(row.Manufacturer),
  r.type = trim(row.Type),

  r.payloadKg = toFloat(row.Payload_kg),
  r.reachMm = toFloat(row.Reach_mm),
  r.repeatabilityMm = toFloat(row.Repeatability_mm),
  r.axis = toInteger(row.Axes),

  r.weightKg = toFloat(row.Weight_kg),
  r.mounting = trim(row.Mounting),
  r.speedGrade = trim(row.Speed_Grade),
  r.costRangeUsd = trim(row.Cost_Range_USD),

  r.cleanroomOption = trim(row.Cleanroom_Option),
  r.cycleTimeSec = toFloat(row.Cycle_Time_sec),
  r.ipRating = trim(row.IP_Rating),
  r.forceSensing = trim(row.Force_Sensing),
  r.esdSafe = trim(row.ESD_Safe),

  r.applicationSuitability = trim(row.Application_Suitability),

  // Optional columns (safe even if missing in this CSV)
  r.specialFeature = row.Special_Features,
  r.safetyFeature = row.Safety_Features,
  r.programmingComplexity = row.Programming_Complexity;

LOAD CSV WITH HEADERS FROM "file:///SCARA_ROBOTS.csv" AS row
WITH row WHERE row.Robot_Model IS NOT NULL AND trim(row.Robot_Model) <> ""
MERGE (r:Robot {robotModel: trim(row.Robot_Model)})
SET
  r.manufacturer = trim(row.Manufacturer),
  r.type = trim(row.Type),
  r.payloadKg = toFloat(row.Payload_kg),
  r.reachMm = toFloat(row.Reach_mm),
  r.repeatabilityMm = toFloat(row.Repeatability_mm),
  r.axis = toInteger(row.Axes),
  r.weightKg = toFloat(row.Weight_kg),
  r.mounting = trim(row.Mounting),
  r.speedGrade = trim(row.Speed_Grade),
  r.costRangeUsd = trim(row.Cost_Range_USD),
  r.cleanroomOption = trim(row.Cleanroom_Option),
  r.cycleTimeSec = toFloat(row.Cycle_Time_sec),
  r.ipRating = trim(row.IP_Rating),
  r.forceSensing = trim(row.Force_Sensing),
  r.esdSafe = trim(row.ESD_Safe),
  r.applicationSuitability = trim(row.Application_Suitability),
  r.specialFeature = row.Special_Features,
  r.safetyFeature = row.Safety_Features,
  r.programmingComplexity = row.Programming_Complexity;

LOAD CSV WITH HEADERS FROM "file:///SPECIALIZED_ROBOTS.csv" AS row
WITH row WHERE row.Robot_Model IS NOT NULL AND trim(row.Robot_Model) <> ""
MERGE (r:Robot {robotModel: trim(row.Robot_Model)})
SET
  r.manufacturer = trim(row.Manufacturer),
  r.type = trim(row.Type),
  r.payloadKg = toFloat(row.Payload_kg),
  r.reachMm = toFloat(row.Reach_mm),
  r.repeatabilityMm = toFloat(row.Repeatability_mm),
  r.axis = toInteger(row.Axes),
  r.weightKg = toFloat(row.Weight_kg),
  r.mounting = trim(row.Mounting),
  r.speedGrade = trim(row.Speed_Grade),
  r.costRangeUsd = trim(row.Cost_Range_USD),
  r.cleanroomOption = trim(row.Cleanroom_Option),
  r.cycleTimeSec = toFloat(row.Cycle_Time_sec),
  r.ipRating = trim(row.IP_Rating),
  r.forceSensing = trim(row.Force_Sensing),
  r.esdSafe = trim(row.ESD_Safe),
  r.applicationSuitability = trim(row.Application_Suitability),
  r.specialFeature = row.Special_Features,
  r.safetyFeature = row.Safety_Features,
  r.programmingComplexity = row.Programming_Complexity;

LOAD CSV WITH HEADERS FROM "file:///COLLABORATIVE_ROBOTS.csv" AS row
WITH row WHERE row.Robot_Model IS NOT NULL AND trim(row.Robot_Model) <> ""
MERGE (r:Robot {robotModel: trim(row.Robot_Model)})
SET
  r.manufacturer = trim(row.Manufacturer),
  r.type = trim(row.Type),
  r.payloadKg = toFloat(row.Payload_kg),
  r.reachMm = toFloat(row.Reach_mm),
  r.repeatabilityMm = toFloat(row.Repeatability_mm),
  r.axis = toInteger(row.Axes),
  r.weightKg = toFloat(row.Weight_kg),
  r.mounting = trim(row.Mounting),
  r.speedGrade = trim(row.Speed_Grade),
  r.costRangeUsd = trim(row.Cost_Range_USD),
  r.cleanroomOption = trim(row.Cleanroom_Option),
  r.cycleTimeSec = toFloat(row.Cycle_Time_sec),
  r.ipRating = trim(row.IP_Rating),
  r.forceSensing = trim(row.Force_Sensing),
  r.esdSafe = trim(row.ESD_Safe),
  r.applicationSuitability = trim(row.Application_Suitability),
  r.specialFeature = row.Special_Features,
  r.safetyFeature = row.Safety_Features,
  r.programmingComplexity = row.Programming_Complexity;

LOAD CSV WITH HEADERS FROM "file:///COMPACT_6AXIS_ROBOTS.csv" AS row
WITH row WHERE row.Robot_Model IS NOT NULL AND trim(row.Robot_Model) <> ""
MERGE (r:Robot {robotModel: trim(row.Robot_Model)})
SET
  r.manufacturer = trim(row.Manufacturer),
  r.type = trim(row.Type),
  r.payloadKg = toFloat(row.Payload_kg),
  r.reachMm = toFloat(row.Reach_mm),
  r.repeatabilityMm = toFloat(row.Repeatability_mm),
  r.axis = toInteger(row.Axes),
  r.weightKg = toFloat(row.Weight_kg),
  r.mounting = trim(row.Mounting),
  r.speedGrade = trim(row.Speed_Grade),
  r.costRangeUsd = trim(row.Cost_Range_USD),
  r.cleanroomOption = trim(row.Cleanroom_Option),
  r.cycleTimeSec = toFloat(row.Cycle_Time_sec),
  r.ipRating = trim(row.IP_Rating),
  r.forceSensing = trim(row.Force_Sensing),
  r.esdSafe = trim(row.ESD_Safe),
  r.applicationSuitability = trim(row.Application_Suitability),
  r.specialFeature = row.Special_Features,
  r.safetyFeature = row.Safety_Features,
  r.programmingComplexity = row.Programming_Complexity;


// ---------------------------------------
// Import applications
// ---------------------------------------
LOAD CSV WITH HEADERS FROM "file:///APPLICATION_REQUIREMENTS.csv" AS row
WITH row WHERE row.Application_ID IS NOT NULL AND trim(row.Application_ID) <> ""
MERGE (a:ApplicationRequirement {applicationId: trim(row.Application_ID)})
SET
  a.applicationType = trim(row.Application_Type),
  a.industrySector = trim(row.Industry_Sector),

  a.payloadMinKg = toFloat(row.Payload_Min_kg),
  a.payloadMaxKg = toFloat(row.Payload_Max_kg),
  a.reachMinMm = toFloat(row.Reach_Min_mm),
  a.reachMaxMm = toFloat(row.Reach_Max_mm),
  a.repeatabilityRequiredMm = toFloat(row.Repeatability_Required_mm),
  a.axesMin = toInteger(row.Axes_Min),

  a.budgetMinUsd = toFloat(row.Budget_Min_USD),
  a.budgetMaxUsd = toFloat(row.Budget_Max_USD),
  a.cycleTimeTargetSec = toFloat(row.Cycle_Time_Target_sec),
  a.ipRatingMin = trim(row.IP_Rating_Min),

  a.cleanroomRequired = trim(row.Cleanroom_Required),
  a.esdProtection = trim(row.ESD_Protection),
  a.forceSensingRequired = trim(row.Force_Sensing_Required),

  a.typicalRobotType = trim(row.Typical_Robot_Types),
  a.speedPriority = trim(row.Speed_Priority),
  a.safetyClassification = trim(row.Safety_Classification);