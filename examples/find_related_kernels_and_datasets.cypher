// Find kernels and datasets that share tags with a competition.
MATCH (c:Competition {Slug: 'titanic'})-[:TAGGED_WITH]->(t:Tag)
MATCH (t)<-[:TAGGED_WITH]-(k:Kernel)-[:CURRENT_VERSION]->(kv:KernelVersion)
MATCH (t)<-[:TAGGED_WITH]-(d:Dataset)-[:CURRENT_VERSION]->(dv:DatasetVersion)
RETURN kv.Title AS NotebookTitle, k.TotalVotes AS NotebookVotes, dv.Title AS DatasetTitle
ORDER BY k.TotalVotes DESC
LIMIT 10;
