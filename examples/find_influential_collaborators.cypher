// Find users who shared gold medal teams.
MATCH (u1:User)-[:MEMBER_OF_TEAM]->(t:Team {Medal: 1})<-[:MEMBER_OF_TEAM]-(u2:User)
WHERE u1.Id <> u2.Id
WITH u1, u2, count(t) AS SharedTeams
MATCH (u1)-[:AUTHORED_KERNEL]->(k:Kernel)
RETURN u1.DisplayName AS User,
       u2.DisplayName AS Collaborator,
       SharedTeams,
       sum(k.TotalVotes) AS TotalKernelVotes,
       SharedTeams * sum(k.TotalVotes) AS CollaborationScore
ORDER BY CollaborationScore DESC
LIMIT 10;
