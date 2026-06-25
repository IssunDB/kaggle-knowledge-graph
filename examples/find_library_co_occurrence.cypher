// Find library pairs imported together in kernel versions.
MATCH (kv:KernelVersion)-[:IMPORTS]->(l1:Library)
MATCH (kv)-[:IMPORTS]->(l2:Library)
WHERE l1.Id < l2.Id
MATCH (k:Kernel)-[:CURRENT_VERSION]->(kv)
RETURN l1.Id AS LibraryA,
       l2.Id AS LibraryB,
       count(kv) AS SharedKernels,
       sum(k.TotalVotes) AS TotalVotes
ORDER BY SharedKernels DESC, TotalVotes DESC
LIMIT 15;
