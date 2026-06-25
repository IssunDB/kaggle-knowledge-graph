// Find libraries imported in kernels for competitions using a specific evaluation metric.
MATCH (c:Competition)
WHERE c.EvaluationAlgorithmName = 'QuadraticWeightedKappa'
MATCH (kv:KernelVersion)-[:USES_COMPETITION]->(c)
MATCH (kv)-[:IMPORTS]->(lib:Library)
RETURN lib.Id AS Library, count(kv) AS ImportCount
ORDER BY ImportCount DESC
LIMIT 10;
