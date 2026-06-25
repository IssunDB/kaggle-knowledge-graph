// Find forum message replies to posts written by members of gold medal teams.
MATCH (u:User)-[:MEMBER_OF_TEAM]->(t:Team {Medal: 1})
MATCH (u)-[:POSTED_MESSAGE]->(m1:ForumMessage)<-[:REPLIES_TO]-(m2:ForumMessage)
MATCH (m2)<-[:POSTED_MESSAGE]-(replier:User)
RETURN u.DisplayName AS Winner,
       m1.Message AS WinnerPost,
       replier.DisplayName AS Replier,
       m2.Message AS ReplyPost,
       m2.Medal AS ReplyMedal
ORDER BY m2.Medal ASC
LIMIT 10;
