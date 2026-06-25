// Query 1: User Node Inspection
// Find user metadata including registration date, country, display name, and performance tier.
MATCH (u:User)
WHERE u.UserName = 'habedi'
RETURN u.Id AS Id,
       u.DisplayName AS DisplayName,
       u.Country AS Country,
       u.RegisterDate AS RegisterDate,
       u.PerformanceTier AS PerformanceTier;

// Query 2: Competition History and Medals
// Find competitions in which the user participated, along with team names, private leaderboard ranks, and medals.
MATCH (u:User)-[:MEMBER_OF_TEAM]->(t:Team)-[:COMPETED_IN]->(c:Competition)
WHERE u.UserName = 'habedi'
RETURN c.Title AS CompetitionTitle,
       t.TeamName AS TeamName,
       t.PrivateLeaderboardRank AS PrivateRank,
       t.Medal AS Medal
ORDER BY t.PrivateLeaderboardRank ASC;

// Query 3: Teammate and Collaboration Network
// Find collaborators who competed on the same teams as the user, ordered by the count of shared competitions.
MATCH (u:User)-[:MEMBER_OF_TEAM]->(t:Team)<-[:MEMBER_OF_TEAM]-(collab:User)
WHERE u.UserName = 'habedi' AND u.Id <> collab.Id
RETURN collab.DisplayName AS Collaborator,
       collab.UserName AS CollaboratorUsername,
       count(t) AS SharedCompetitions
ORDER BY SharedCompetitions DESC;

// Query 4: Kernel Authorship and Engagement
// Find kernels authored by the user, including titles, total views, total votes, and total comments.
MATCH (u:User)-[:AUTHORED_KERNEL]->(k:Kernel)-[:CURRENT_VERSION]->(kv:KernelVersion)
WHERE u.UserName = 'habedi'
RETURN k.Id AS KernelId,
       kv.Title AS CurrentTitle,
       k.TotalViews AS Views,
       k.TotalVotes AS Votes,
       k.TotalComments AS Comments;

// Query 5: Forum Posting Activity
// Find forum message details, including post dates, content, and medals, for messages authored by the user.
MATCH (u:User)-[:POSTED_MESSAGE]->(m:ForumMessage)
WHERE u.UserName = 'habedi'
RETURN m.PostDate AS PostDate,
       m.Message AS MessageContent,
       m.Medal AS Medal
ORDER BY m.PostDate DESC;

// Query 6: Forum Topics Distribution
// Find forum topics where the user posted, ordered by the message count.
MATCH (u:User)-[:POSTED_MESSAGE]->(m:ForumMessage)<-[:HAS_MESSAGE]-(topic:ForumTopic)
WHERE u.UserName = 'habedi'
RETURN topic.Title AS TopicTitle,
       count(m) AS MessagesPosted
ORDER BY MessagesPosted DESC;
