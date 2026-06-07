# Incident 9913

Postmortem for incident 9913: the login service returned intermittent timeouts
under load. Root cause was connection pool exhaustion; mitigation was a pool size
increase and a retry budget.
