# Incident 9912

Postmortem for incident 9912: the login service returned intermittent timeouts
under load. Root cause was connection pool exhaustion; mitigation was a pool size
increase and a retry budget.
