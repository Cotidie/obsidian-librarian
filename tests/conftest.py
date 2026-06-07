from dotenv import load_dotenv

# Load .env before test collection so VOYAGE_API_KEY-gated tests run when a key
# is present in the project-root .env.
load_dotenv()
