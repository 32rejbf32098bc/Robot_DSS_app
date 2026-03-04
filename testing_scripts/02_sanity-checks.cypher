MATCH (r:Robot) RETURN count(r) AS robots;
MATCH (a:ApplicationRequirement) RETURN count(a) AS applications;

CALL db.relationshipTypes();

MATCH (r:Robot) RETURN keys(r) AS robotKeys LIMIT 1;
MATCH (a:ApplicationRequirement) RETURN keys(a) AS appKeys LIMIT 1;