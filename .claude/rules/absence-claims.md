# Absence claims

A denied, errored, or empty-because-blocked tool call is UNVERIFIED, never a negative finding.

- Write "could not check X, the call was denied" and name the route that would settle it.
- Never write "X is absent" from a wall you could not see past.
- Before treating an empty result as absence, run a control probe: query something you KNOW exists by the same route. If the control also comes back empty, the route is blind and every empty result from it is meaningless.
- Absence claims carry their scope: "no zod in package.json (read directly)" is a finding. "No zod in this repo" is not, unless every path was actually readable.
- Claims inherited from a subagent carry the subagent's doubt. Passing them on unmarked makes them yours.