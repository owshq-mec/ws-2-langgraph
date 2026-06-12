#!/bin/sh
# Wait for Neo4j, then run the seed Cypher.
set -e

NEO4J_HOST="${NEO4J_HOST:-neo4j}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-dataops123}"
CYPHER_FILE="${CYPHER_FILE:-/scripts/init-neo4j.cypher}"

echo "Waiting for Neo4j at ${NEO4J_HOST}..."
until cypher-shell -a "bolt://${NEO4J_HOST}:7687" -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" "RETURN 1" > /dev/null 2>&1; do
    sleep 3
done

echo "Running ${CYPHER_FILE}..."
cypher-shell -a "bolt://${NEO4J_HOST}:7687" -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" -f "${CYPHER_FILE}"
echo "Neo4j seeded successfully."
