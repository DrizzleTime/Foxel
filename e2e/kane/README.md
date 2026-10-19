# End-to-end (e2e) tests for web

Browser tests written in plain English for [Kane CLI](https://www.testmuai.com/kane-cli/).

| Test | What it covers |
|---|---|
| `setup_test.md` | System initialization: database, the first storage mount and the admin account |
| `folder_test.md` | Initialization, then opening the local mount and creating a folder |

## Run

Start a fresh instance on port 4890:

```bash
docker run -d --name foxel-e2e -p 4890:80 -e SECRET_KEY=e2e-secret -e TEMP_LINK_SECRET_KEY=e2e-secret ghcr.io/drizzletime/foxel:latest
npm install -g @testmuai/kane-cli
kane-cli login
kane-cli testmd run e2e/kane/setup_test.md
kane-cli testmd run e2e/kane/folder_test.md
```

Both tests start from system initialization, so recreate the container before each run. They expect the welcome notice from foxel.cc to pop up after the first login.
