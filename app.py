from flask import Flask
from flask import jsonify
from flask_limiter.errors import RateLimitExceeded

from rate_limit import limiter
from routes import api


def create_app():
    app = Flask(__name__)
    limiter.init_app(app)
    app.register_blueprint(api)

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(error):
        return jsonify({"error": "Rate limit exceeded.", "detail": str(error.description)}), 429

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
