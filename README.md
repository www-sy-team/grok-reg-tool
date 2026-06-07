# grok-reg-tool

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](docker/Dockerfile)
[![Node.js](https://img.shields.io/badge/Node.js-20+-339933.svg)](package.json)
[![Python](https://img.shields.io/badge/Python-3.13+-3776AB.svg)](register/requirements.txt)

`grok-reg-tool` is a self-hosted Grok registration Web console for Docker users. It combines a React Web UI, Node.js API server, DrissionPage-based Python automation, mail backend integration, and local account pool management in one deployable project.

中文介绍：`grok-reg-tool` 是一个面向自托管场景的 Grok 注册机 Web 控制台，支持 Docker 一键部署、邮箱后端配置、Python 自动化注册脚本运行、日志查看、SSO token 提取和本地账号号池管理。项目内置 `register/` 注册机目录，构建 Docker 镜像时会自动安装 Python 依赖，不需要额外挂载 `grok-register`。

> This project is not affiliated with xAI, Grok, or X. Use it only for lawful automation research, personal learning, and environments where you have permission. Do not use it for spam, abuse, credential stuffing, platform disruption, or any activity that violates applicable laws or service terms.

## Features

- Docker-ready Grok registration tool with built-in Python runtime dependencies.
- Web dashboard for registration status, runtime logs, account records, and SSO output.
- Self-hosted mail backend configuration for verification-code polling.
- DrissionPage automation entrypoint included in `register/`.
- Local data persistence through `docker/data/`.
- Health check for script path and writable data directory.
- Configurable HTTP proxy, browser proxy, Chromium path, and run count.
- Minimal release layout: no external `grok-register` mount required.

## Keywords

Grok registration tool, Grok register WebUI, xAI automation dashboard, DrissionPage Docker automation, self-hosted registration console, Grok account pool manager, SSO token management, Docker Grok tool, Grok 注册机, Grok 自动注册, xAI 自动化, DrissionPage 注册工具, Docker 自部署 Web 控制台。

## Quick Start

Clone the repository:

```bash
git clone https://github.com/FengZi1221/grok-reg-tool.git
cd grok-reg-tool/docker
```

Create your Docker environment file:

```bash
cp .env.example .env
```

Edit `docker/.env` and fill in your mail backend settings:

```env
WEB_PORT=6657
RUN_COUNT=10
MAIL_API_BASE=
MAIL_ADMIN_AUTH=
MAIL_DOMAIN=
HTTP_PROXY=
BROWSER_PROXY=
```

Start the service:

```bash
docker compose up -d --build
```

Open the Web UI:

```text
http://your-server-ip:6657
```

The default Web account information is printed in:

```bash
docker logs grok-reg-tool
```

After first login, follow the Web UI prompt to change the username and password.

## Docker Deployment Notes

The image is self-contained:

- Node.js server and React Web UI are built during image build.
- Python 3.13 runtime is included.
- `register/requirements.txt` is installed automatically.
- Chromium and Xvfb are installed for browser automation.
- The registration entrypoint inside the container is `/app/register/runner.py`.
- Runtime data is stored in `/data`, mounted as `docker/data` by default.

Important paths:

| Purpose | Container Path | Host Path |
| --- | --- | --- |
| Web UI and API data | `/data` | `docker/data` |
| SSO output | `/data/sso` | `docker/data/sso` |
| Built-in register scripts | `/app/register` | included in image |
| Web service port | `6657` | `${WEB_PORT:-6657}` |

## Configuration

Most settings can be configured in the Web UI after login. Docker users can also set defaults through `docker/.env`.

| Variable | Description | Default |
| --- | --- | --- |
| `WEB_PORT` | Host port exposed by Docker Compose | `6657` |
| `RUN_COUNT` | Number of registration rounds per run | `10` |
| `MAIL_API_BASE` | Mail backend API base URL | empty |
| `MAIL_ADMIN_AUTH` | Mail backend admin auth token/password | empty |
| `MAIL_DOMAIN` | Mail domain used for generated addresses | empty |
| `HTTP_PROXY` | HTTP proxy used by backend requests | empty |
| `BROWSER_PROXY` | Browser proxy used by DrissionPage/Chromium | empty |

Advanced defaults used by the container:

| Variable | Default |
| --- | --- |
| `PYTHON_PATH` | `/usr/local/bin/python3` |
| `REGISTER_DIR` | `/app/register` |
| `SSO_DIR` | `/data/sso` |
| `BROWSER_PATH` | `/usr/bin/chromium` |

## Local Development

Install Node.js dependencies:

```bash
npm install
```

Build the Web UI and server:

```bash
npm run server:build
```

Run the server in development mode:

```bash
npm run server:dev
```

Python dependencies for local script testing:

```bash
python -m pip install -r register/requirements.txt
```

## Project Structure

```text
grok-reg-tool/
├── docker/                 # Dockerfile, compose file, container entrypoint
├── register/               # Built-in Python registration automation
│   ├── runner.py           # Stable Python entrypoint
│   ├── DrissionPage_example.py
│   ├── email_register.py
│   └── requirements.txt
├── server/                 # Express API server and WebSocket runner bridge
├── src/                    # React Web UI and shared TypeScript types
├── package.json
└── README.md
```

## Data, Secrets, and Privacy

Do not commit runtime secrets or account data. The repository ignores:

- `.env`
- `docker/.env`
- `docker/data/`
- `register/config.json`
- `register/logs/`
- `register/sso/`
- `out/`
- `node_modules/`
- `server/dist/`

If you deploy this tool on a public server, protect the Web UI with a strong password, restrict network exposure where possible, and rotate any leaked mail backend or proxy credentials immediately.

## Troubleshooting

### `Runner error: 未找到注册脚本`

Rebuild the Docker image after pulling the latest source:

```bash
cd docker
docker compose down
docker compose up -d --build
```

The current release uses `/app/register`, not `/app/grok-register`. You should not mount an external `./grok-register` folder over `/app/register`.

### Web UI cannot connect to the mail backend

Check `MAIL_API_BASE`, `MAIL_ADMIN_AUTH`, and `MAIL_DOMAIN` in `docker/.env`, then restart the container:

```bash
docker compose restart
```

### Chromium fails in Docker

The image installs Chromium and Xvfb by default. If you use a custom image or custom browser path, verify `BROWSER_PATH` points to a valid executable.

## Responsible Use

This repository is published for technical research, self-hosted automation experiments, and learning how to combine Docker, React, Node.js, Python, and DrissionPage into a Web-controlled automation workflow.

You are responsible for how you run it. Before using this project, review the terms of service of any platform involved and comply with local laws. The maintainer does not endorse abuse, large-scale account creation, spam, bypassing access controls, or disruption of third-party services.

## Contributing

Issues and pull requests are welcome:

- Bug reports should include Docker logs, environment details, and reproduction steps.
- Feature requests should describe the use case and expected behavior.
- Please do not submit secrets, live SSO tokens, private mail credentials, or personal account data.

Repository: <https://github.com/FengZi1221/grok-reg-tool>

## License

This project is released under the [MIT License](LICENSE).
