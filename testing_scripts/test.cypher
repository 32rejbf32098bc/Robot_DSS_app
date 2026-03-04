MATCH (r:Robot)
MATCH (a:ApplicationRequirement)

WHERE a.applicationId = "S01"

AND r.payloadKg >= a.payloadMinKg AND r.payloadKg <= a.payloadMaxKg
AND r.reachMm >= a.reachMinMm AND r.reachMm <= a.reachMaxMm
AND r.repeatabilityMm <= a.repeatabilityRequiredMm
AND r.axis >= a.axesMin

RETURN
r.robotModel,
a.applicationId,
a.applicationType;

MATCH (a:ApplicationRequirement)
RETURN a.applicationId, a.applicationType;

MATCH (r:Robot)
RETURN r.robotModel;

MATCH (r:Robot)-[:SUITABLE_FOR]->(a:ApplicationRequirement)
RETURN r,a
LIMIT 50;

MATCH (r:Robot)
WHERE NOT (r)-[:SUITABLE_FOR]->(:ApplicationRequirement)
RETURN
r.robotModel,
r.payloadKg,
r.reachMm,
r.repeatabilityMm,
r.axis
ORDER BY r.robotModel;

// This query returns all robots that are not suitable for any application, along with their key attributes for further analysis.

MATCH (r:Robot)
MATCH (a:ApplicationRequirement {applicationId:"S01"})

WITH
r.robotModel AS robot,
r.type AS robotType,

[
CASE WHEN r.payloadKg < a.payloadMinKg THEN "Payload too low" END,
CASE WHEN r.payloadKg > a.payloadMaxKg THEN "Payload too high" END,
CASE WHEN r.reachMm < a.reachMinMm THEN "Reach too short" END,
CASE WHEN r.reachMm > a.reachMaxMm THEN "Reach too long" END,
CASE WHEN r.repeatabilityMm > a.repeatabilityRequiredMm THEN "Not precise enough" END,
CASE WHEN r.axis < a.axesMin THEN "Not enough axes" END
] AS reasons

RETURN
robot,
robotType,

CASE
WHEN size([reason IN reasons WHERE reason IS NOT NULL]) = 0
THEN "Suitable"
ELSE reasons
END AS suitability

ORDER BY robot;