# Security Policy

## Reporting a Security Issue

Please do not publicly disclose sensitive security issues before there is an
opportunity to investigate and address them.

For security-sensitive reports, contact the project owner privately before
public disclosure.

When reporting a vulnerability, provide enough information to reproduce the
issue without including unnecessary personal information or credentials.

## Do Not Include

Never include the following in a public issue or security report:

- passwords
- API keys
- authentication tokens
- private certificates
- personal information
- private user images
- private build credentials
- other sensitive secrets

## Public Issues

Use GitHub Issues for normal:

- bug reports
- feature requests
- documentation issues
- reproducible non-sensitive problems

Security-sensitive vulnerabilities should be reported privately.

## Scope

Security concerns may include:

- arbitrary code execution
- unsafe file handling
- malicious image-processing payloads
- dependency vulnerabilities affecting Lumen Forge
- unintended access to local files
- credential or secret exposure
- other vulnerabilities that could compromise a user's system or data

## Third-Party Dependencies

Lumen Forge uses third-party libraries and may optionally use additional
packages for RAW processing and computer-vision functionality.

Security issues originating in a third-party dependency should also be
reported to the relevant upstream project when appropriate.

## Responsible Disclosure

Please allow reasonable time for investigation and remediation before
publicly disclosing a confirmed vulnerability.