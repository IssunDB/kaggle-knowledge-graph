MATCH (n)
RETURN labels(n) AS labels, count(*) AS count
ORDER BY labels;

MATCH ()-[r]->()
RETURN type(r) AS relationship, count(*) AS count
ORDER BY relationship;
