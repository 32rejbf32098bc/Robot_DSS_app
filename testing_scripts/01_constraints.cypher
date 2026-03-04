CREATE CONSTRAINT robot_model_unique IF NOT EXISTS
FOR (r:Robot) REQUIRE r.Robot_Model IS UNIQUE;

CREATE CONSTRAINT app_id_unique IF NOT EXISTS
FOR (a:ApplicationRequirement) REQUIRE a.Application_ID IS UNIQUE;

MATCH (r:Robot)
SET r.name = r.robotModel;

MATCH (a:ApplicationRequirement)
SET a.name = a.applicationId;