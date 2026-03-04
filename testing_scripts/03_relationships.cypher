// Create SUITABLE_FOR relationships between robots and application requirements
// based on the suitability criteria.
MATCH (r:Robot)
MATCH (a:ApplicationRequirement)
WHERE
  r.payloadKg >= a.payloadMinKg AND r.payloadKg <= a.payloadMaxKg AND
  r.reachMm   >= a.reachMinMm   AND r.reachMm   <= a.reachMaxMm AND
  r.repeatabilityMm <= a.repeatabilityRequiredMm AND
  r.axis >= a.axesMin

MERGE (r)-[:SUITABLE_FOR]->(a);

MATCH (:Robot)-[rel:SUITABLE_FOR]->(:ApplicationRequirement)
RETURN count(rel) AS suitableRels;

// remove suitable_for relationships if you want to 
// re-run the suitability logic after changing robot or application requirement data
MATCH ()-[rel:SUITABLE_FOR]->()
DELETE rel;

// Adds individual suitability reasons as properties on the relationship
// for more detailed analysis

// payload suitability
MATCH (r:Robot)
MATCH (a:ApplicationRequirement)
WHERE r.payloadKg >= a.payloadMinKg AND r.payloadKg <= a.payloadMaxKg
MERGE (r)-[:MEETS_PAYLOAD]->(a);

// reach suitability
MATCH (r:Robot)
MATCH (a:ApplicationRequirement)
WHERE r.reachMm >= a.reachMinMm AND r.reachMm <= a.reachMaxMm
MERGE (r)-[:MEETS_REACH]->(a);

// repeatability suitability
MATCH (r:Robot)
MATCH (a:ApplicationRequirement)
WHERE r.repeatabilityMm <= a.repeatabilityRequiredMm
MERGE (r)-[:MEETS_PRECISION]->(a);

// Axes suitability
MATCH (r:Robot)
MATCH (a:ApplicationRequirement)
WHERE r.axis >= a.axesMin
MERGE (r)-[:MEETS_AXES]->(a);

// full suitability (all criteria met)
MATCH (r:Robot)
MATCH (a:ApplicationRequirement)
WHERE
  (r)-[:MEETS_PAYLOAD]->(a) AND
  (r)-[:MEETS_REACH]->(a) AND
  (r)-[:MEETS_PRECISION]->(a) AND
  (r)-[:MEETS_AXES]->(a)
MERGE (r)-[:FULLY_SUITABLE_FOR]->(a);