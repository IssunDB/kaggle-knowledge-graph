LOAD CSV WITH HEADERS FROM 'file:///edges_user_authored_kernel.csv' AS row
CALL {
  WITH row
  MATCH (a:User {id: toInteger(row.from_user_id)})
  MATCH (b:Kernel {id: toInteger(row.to_kernel_id)})
  MERGE (a)-[:AUTHORED_KERNEL]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_has_version.csv' AS row
CALL {
  WITH row
  MATCH (a:Kernel {id: toInteger(row.from_kernel_id)})
  MATCH (b:KernelVersion {id: toInteger(row.to_kernel_version_id)})
  MERGE (a)-[:HAS_VERSION]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_current_version.csv' AS row
CALL {
  WITH row
  MATCH (a:Kernel {id: toInteger(row.from_kernel_id)})
  MATCH (b:KernelVersion {id: toInteger(row.to_kernel_version_id)})
  MERGE (a)-[:CURRENT_VERSION]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_first_version.csv' AS row
CALL {
  WITH row
  MATCH (a:Kernel {id: toInteger(row.from_kernel_id)})
  MATCH (b:KernelVersion {id: toInteger(row.to_kernel_version_id)})
  MERGE (a)-[:FIRST_VERSION]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_version_authored_by_user.csv' AS row
CALL {
  WITH row
  MATCH (a:KernelVersion {id: toInteger(row.from_kernel_version_id)})
  MATCH (b:User {id: toInteger(row.to_user_id)})
  MERGE (a)-[:AUTHORED_BY]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_version_imports_library.csv' AS row
CALL {
  WITH row
  MATCH (a:KernelVersion {id: toInteger(row.from_kernel_version_id)})
  MATCH (b:Library {id: row.to_library_id})
  MERGE (a)-[:IMPORTS]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_version_uses_dataset_version.csv' AS row
CALL {
  WITH row
  MATCH (a:KernelVersion {id: toInteger(row.from_kernel_version_id)})
  MATCH (b:DatasetVersion {id: toInteger(row.to_dataset_version_id)})
  MERGE (a)-[:USES_DATASET_VERSION]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_dataset_has_version.csv' AS row
CALL {
  WITH row
  MATCH (a:Dataset {id: toInteger(row.from_dataset_id)})
  MATCH (b:DatasetVersion {id: toInteger(row.to_dataset_version_id)})
  MERGE (a)-[:HAS_VERSION]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_dataset_current_version.csv' AS row
CALL {
  WITH row
  MATCH (a:Dataset {id: toInteger(row.from_dataset_id)})
  MATCH (b:DatasetVersion {id: toInteger(row.to_dataset_version_id)})
  MERGE (a)-[:CURRENT_VERSION]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_version_uses_competition.csv' AS row
CALL {
  WITH row
  MATCH (a:KernelVersion {id: toInteger(row.from_kernel_version_id)})
  MATCH (b:Competition {id: toInteger(row.to_competition_id)})
  MERGE (a)-[:USES_COMPETITION]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_tagged_with_tag.csv' AS row
CALL {
  WITH row
  MATCH (a:Kernel {id: toInteger(row.from_kernel_id)})
  MATCH (b:Tag {id: toInteger(row.to_tag_id)})
  MERGE (a)-[:TAGGED_WITH]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_dataset_tagged_with_tag.csv' AS row
CALL {
  WITH row
  MATCH (a:Dataset {id: toInteger(row.from_dataset_id)})
  MATCH (b:Tag {id: toInteger(row.to_tag_id)})
  MERGE (a)-[:TAGGED_WITH]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_competition_tagged_with_tag.csv' AS row
CALL {
  WITH row
  MATCH (a:Competition {id: toInteger(row.from_competition_id)})
  MATCH (b:Tag {id: toInteger(row.to_tag_id)})
  MERGE (a)-[:TAGGED_WITH]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_competition_has_forum.csv' AS row
CALL {
  WITH row
  MATCH (a:Competition {id: toInteger(row.from_competition_id)})
  MATCH (b:Forum {id: toInteger(row.to_forum_id)})
  MERGE (a)-[:HAS_FORUM]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_forum_has_topic.csv' AS row
CALL {
  WITH row
  MATCH (a:Forum {id: toInteger(row.from_forum_id)})
  MATCH (b:ForumTopic {id: toInteger(row.to_forum_topic_id)})
  MERGE (a)-[:HAS_TOPIC]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_kernel_has_forum_topic.csv' AS row
CALL {
  WITH row
  MATCH (a:Kernel {id: toInteger(row.from_kernel_id)})
  MATCH (b:ForumTopic {id: toInteger(row.to_forum_topic_id)})
  MERGE (a)-[:HAS_FORUM_TOPIC]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_forum_topic_has_message.csv' AS row
CALL {
  WITH row
  MATCH (a:ForumTopic {id: toInteger(row.from_forum_topic_id)})
  MATCH (b:ForumMessage {id: toInteger(row.to_forum_message_id)})
  MERGE (a)-[:HAS_MESSAGE]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_user_posted_message.csv' AS row
CALL {
  WITH row
  MATCH (a:User {id: toInteger(row.from_user_id)})
  MATCH (b:ForumMessage {id: toInteger(row.to_forum_message_id)})
  MERGE (a)-[:POSTED_MESSAGE]->(b)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///edges_forum_message_replies_to.csv' AS row
CALL {
  WITH row
  MATCH (a:ForumMessage {id: toInteger(row.from_forum_message_id)})
  MATCH (b:ForumMessage {id: toInteger(row.to_forum_message_id)})
  MERGE (a)-[:REPLIES_TO]->(b)
} IN TRANSACTIONS OF 10000 ROWS;
