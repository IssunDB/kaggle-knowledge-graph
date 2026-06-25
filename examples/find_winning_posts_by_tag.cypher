// Find forum topics and scores from gold medal teams in competitions with a specific tag.
MATCH (t:Tag {Id: 'nlp'})<-[:TAGGED_WITH]-(c:Competition)
MATCH (team:Team {Medal: 1})-[:COMPETED_IN]->(c)
MATCH (c)-[:HAS_FORUM]->(f:Forum)-[:HAS_TOPIC]->(topic:ForumTopic)
RETURN topic.Title AS TopicTitle, topic.Score AS Score
ORDER BY topic.Score DESC
LIMIT 10;
