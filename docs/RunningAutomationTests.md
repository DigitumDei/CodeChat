# Running the automation tests

This document outlines the steps to execute the automation tests for the CodeChat project using Docker. This approach ensures a consistent testing environment that is as close as possible to what runs in the CI environment.

```powershell
docker build --target test -t codechat:test .
docker run -it codechat:test
```