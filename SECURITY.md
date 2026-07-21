# Security Policy

Do not open public issues containing credentials or vulnerability details. Report security
findings privately to the project owner. Rotate any exposed OIDC, provider, database, screenshot,
or session secret immediately. Supported security updates apply to the current `0.2.x` release line.

RegHub validates screenshot URLs before delegation, but the isolated screenshot service must also
resolve DNS safely, block private/internal destinations after resolution, restrict outbound network
access, and enforce time, redirect, and response-size limits.
