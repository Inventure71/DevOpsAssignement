"""Run the single-process development server with python -m backend."""
import uvicorn

from backend.core.config import Config


def main():
    config = Config.from_env()
    uvicorn.run('backend.app:app', host='0.0.0.0', port=config.port, workers=1, access_log=False)


if __name__ == '__main__':
    main()
