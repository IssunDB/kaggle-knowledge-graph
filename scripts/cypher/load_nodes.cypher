LOAD CSV WITH HEADERS FROM 'file:///nodes_user.csv' AS row
CALL {
  WITH row
  MERGE (n:User {id: toInteger(row.Id)})
  SET n.userName = row.UserName,
      n.displayName = row.DisplayName,
      n.registerDate = row.RegisterDate,
      n.performanceTier = toInteger(row.PerformanceTier),
      n.country = row.Country
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_kernel.csv' AS row
CALL {
  WITH row
  MERGE (n:Kernel {id: toInteger(row.Id)})
  SET n.slug = row.CurrentUrlSlug,
      n.createdAt = row.CreationDate,
      n.madePublicAt = row.MadePublicDate,
      n.medal = toInteger(row.Medal),
      n.totalViews = toInteger(row.TotalViews),
      n.totalComments = toInteger(row.TotalComments),
      n.totalVotes = toInteger(row.TotalVotes)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_kernel_version.csv' AS row
CALL {
  WITH row
  MERGE (n:KernelVersion {id: toInteger(row.Id)})
  SET n.kernelId = toInteger(row.ScriptId),
      n.versionNumber = toInteger(row.VersionNumber),
      n.title = row.Title,
      n.createdAt = row.CreationDate,
      n.totalLines = toInteger(row.TotalLines),
      n.totalVotes = toInteger(row.TotalVotes),
      n.isInternetEnabled = toBoolean(row.IsInternetEnabled),
      n.runningTimeMs = toInteger(row.RunningTimeInMilliseconds),
      n.dockerImage = row.DockerImage
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_dataset.csv' AS row
CALL {
  WITH row
  MERGE (n:Dataset {id: toInteger(row.Id)})
  SET n.type = row.Type,
      n.createdAt = row.CreationDate,
      n.lastActivityDate = row.LastActivityDate,
      n.totalViews = toInteger(row.TotalViews),
      n.totalDownloads = toInteger(row.TotalDownloads),
      n.totalVotes = toInteger(row.TotalVotes),
      n.totalKernels = toInteger(row.TotalKernels),
      n.medal = toInteger(row.Medal)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_dataset_version.csv' AS row
CALL {
  WITH row
  MERGE (n:DatasetVersion {id: toInteger(row.Id)})
  SET n.datasetId = toInteger(row.DatasetId),
      n.versionNumber = toInteger(row.VersionNumber),
      n.title = row.Title,
      n.slug = row.Slug,
      n.subtitle = row.Subtitle,
      n.licenseName = row.LicenseName,
      n.createdAt = row.CreationDate,
      n.totalCompressedBytes = toInteger(row.TotalCompressedBytes),
      n.totalUncompressedBytes = toInteger(row.TotalUncompressedBytes)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_competition.csv' AS row
CALL {
  WITH row
  MERGE (n:Competition {id: toInteger(row.Id)})
  SET n.slug = row.Slug,
      n.title = row.Title,
      n.subtitle = row.Subtitle,
      n.hostSegmentTitle = row.HostSegmentTitle,
      n.enabledAt = row.EnabledDate,
      n.deadlineAt = row.DeadlineDate,
      n.evaluationAlgorithm = row.EvaluationAlgorithmName,
      n.evaluationAlgorithmIsMax = toBoolean(row.EvaluationAlgorithmIsMax),
      n.rewardType = row.RewardType,
      n.rewardQuantity = toFloat(row.RewardQuantity),
      n.totalTeams = toInteger(row.TotalTeams),
      n.totalCompetitors = toInteger(row.TotalCompetitors),
      n.totalSubmissions = toInteger(row.TotalSubmissions)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_tag.csv' AS row
CALL {
  WITH row
  MERGE (n:Tag {id: toInteger(row.Id)})
  SET n.name = row.Name,
      n.slug = row.Slug,
      n.fullPath = row.FullPath,
      n.description = row.Description
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_library.csv' AS row
CALL {
  WITH row
  MERGE (n:Library {id: row.Id})
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_forum.csv' AS row
CALL {
  WITH row
  MERGE (n:Forum {id: toInteger(row.Id)})
  SET n.title = row.Title
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_forum_topic.csv' AS row
CALL {
  WITH row
  MERGE (n:ForumTopic {id: toInteger(row.Id)})
  SET n.title = row.Title,
      n.createdAt = row.CreationDate,
      n.lastCommentAt = row.LastCommentDate,
      n.isSticky = toBoolean(row.IsSticky),
      n.totalViews = toInteger(row.TotalViews),
      n.score = toInteger(row.Score),
      n.totalMessages = toInteger(row.TotalMessages),
      n.totalReplies = toInteger(row.TotalReplies)
} IN TRANSACTIONS OF 10000 ROWS;

LOAD CSV WITH HEADERS FROM 'file:///nodes_forum_message.csv' AS row
CALL {
  WITH row
  MERGE (n:ForumMessage {id: toInteger(row.Id)})
  SET n.postedAt = row.PostDate,
      n.medal = toInteger(row.Medal),
      n.message = row.Message,
      n.rawMarkdown = row.RawMarkdown
} IN TRANSACTIONS OF 10000 ROWS;
