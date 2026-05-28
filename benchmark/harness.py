"""
Minimal Draguniteus Benchmark Harness
Runs benchmark tasks and scores based on code quality from streaming output.
"""
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from draguniteus.client import DraguniteusClient
from draguniteus.config import Config

BENCHMARK_DIR = Path("C:/tmp/benchmark_workspace")
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)


def run_task(prompt: str, timeout: int = 300) -> dict:
    """Run a task through Draguniteus streaming client."""
    client = DraguniteusClient(Config())
    messages = [{"role": "user", "content": prompt}]

    start_time = time.time()
    full_text = ""
    thinking_text = ""

    try:
        stream = client.stream(
            messages=messages,
            model="MiniMax-M2.7",
            max_tokens=8192,
            system="""You are Draguniteus, an expert coding agent. Write complete, working code files.
When asked to create files, write them with proper syntax and imports.
After writing code, verify it by running any available verification commands.""",
        )

        for event in stream:
            if hasattr(event, 'type'):
                if event.type == 'content_block_delta':
                    delta = getattr(event, 'delta', None)
                    if delta:
                        if hasattr(delta, 'text') and delta.text:
                            full_text += delta.text
                        elif hasattr(delta, 'thinking') and delta.thinking:
                            thinking_text += delta.thinking
                elif event.type == 'message_stop':
                    break

        elapsed = time.time() - start_time

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "elapsed": elapsed,
            "text": full_text[:5000],
            "thinking": thinking_text[:2000],
            "error": str(e),
            "success": False,
        }

    return {
        "elapsed": elapsed,
        "text": full_text,
        "thinking": thinking_text,
        "error": None,
        "success": True,
    }


def score_code_quality(text: str, task_id: str) -> dict:
    """Score the quality of generated code from streaming text."""
    scores = {}

    if task_id == "fastapi_auth":
        has_fastapi = "fastapi" in text.lower()
        has_decorator = "@app.post" in text or "@app.get" in text
        has_auth = "jwt" in text.lower() or "password" in text.lower()
        has_models = "class user" in text.lower() or "class token" in text.lower()
        code_blocks = text.count("```")
        scores = {
            "has_fastapi": has_fastapi,
            "has_decorators": has_decorator,
            "has_auth": has_auth,
            "has_models": has_models,
            "code_blocks": code_blocks,
        }
        quality = (has_fastapi + has_decorator + has_auth + has_models) * 20 + min(code_blocks * 2, 20)
        return {"quality_score": min(quality, 100), "details": scores}

    elif task_id == "python_package":
        has_import = "from . import" in text or "from .animals import" in text
        has_class = "class dog" in text.lower() or "class cat" in text.lower()
        has_speak = "def speak" in text.lower()
        has_main = "__name__" in text
        code_blocks = text.count("```")
        quality = (has_import + has_class + has_speak + has_main) * 20 + min(code_blocks * 2, 20)
        return {"quality_score": min(quality, 100), "details": scores}

    elif task_id == "git_script":
        has_function = "def " in text
        has_git = "git " in text
        has_error = "if" in text and ("!=" in text or "==" in text)
        code_blocks = text.count("```")
        quality = (has_function + has_git + has_error) * 20 + min(code_blocks * 3, 30)
        return {"quality_score": min(quality, 100), "details": scores}

    elif task_id == "react_components":
        has_tsx = ".tsx" in text
        has_interface = "interface" in text or "Props" in text
        has_react = "React" in text or "react" in text
        components = sum(1 for c in ["Button", "Card", "Modal", "Input", "Select"] if c in text)
        code_blocks = text.count("```")
        quality = (has_tsx + has_interface + has_react) * 15 + components * 12 + min(code_blocks * 2, 15)
        return {"quality_score": min(quality, 100), "details": {"components": components, "code_blocks": code_blocks}}

    elif task_id == "self_correct_loop":
        has_function = "def calculate_stats" in text
        has_bug = "number)" in text or "sum(number)" in text
        has_fix = "def calculate_stats(numbers):" in text
        has_result = "(15, 3.0)" in text or "(15," in text
        quality = 25 + (25 if has_function else 0) + (25 if has_bug else 0) + (25 if has_fix else 0) + (25 if has_result else 0)
        return {"quality_score": min(quality, 100), "details": {"has_function": has_function, "has_bug": has_bug, "has_fix": has_fix, "has_result": has_result}}

    elif task_id == "async_fastapi":
        has_async = "async def" in text
        has_aiosqlite = "aiosqlite" in text
        has_engine = "create_async_engine" in text
        has_models = "class item" in text.lower() or "__tablename__" in text
        code_blocks = text.count("```")
        quality = (has_async + has_aiosqlite + has_engine + has_models) * 20 + min(code_blocks * 2, 20)
        return {"quality_score": min(quality, 100), "details": {"code_blocks": code_blocks}}

    elif task_id == "debug_and_fix":
        has_errors = "error" in text.lower() or "bug" in text.lower() or "fix" in text.lower()
        has_flask = "flask" in text.lower()
        has_route = "@app.route" in text or "route" in text
        has_jsonify = "jsonify" in text
        quality = (has_errors + has_flask + has_route + has_jsonify) * 20 + (20 if "def " in text else 0)
        return {"quality_score": min(quality, 100), "details": {"mentions_errors": has_errors, "has_flask": has_flask}}

    elif task_id == "docker_script":
        has_docker = "docker" in text.lower()
        has_compose = "compose" in text.lower() or "services:" in text
        has_dockerfile = "dockerfile" in text.lower() or "FROM" in text
        has_expose = "EXPOSE" in text or "expose" in text
        code_blocks = text.count("```")
        quality = (has_docker + has_compose + has_dockerfile + has_expose) * 20 + min(code_blocks * 2, 20)
        return {"quality_score": min(quality, 100), "details": {"code_blocks": code_blocks}}

    return {"quality_score": 50, "details": {}}


def run_benchmark():
    """Run the full benchmark."""
    # Inline task definitions to avoid import issues
    TASKS = [
        type('Task', (), {
            'id': 'fastapi_auth',
            'name': 'FastAPI Authentication Service',
            'difficulty': 'hard',
            'prompt': '''Create a complete FastAPI authentication service.

Create these files in /tmp/benchmark_workspace/fastapi_auth/:

1. requirements.txt:
fastapi==0.115.0
uvicorn[standard]==0.30.0
pyjwt==2.9.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9

2. main.py:
```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import sys
sys.path.insert(0, ".")
from models import User, Token
from schemas import UserCreate, UserResponse, TokenResponse

app = FastAPI(title="Auth Service")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

SECRET_KEY = "benchmark-secret-key-do-not-use-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

users_db = {}

@app.post("/auth/register", response_model=TokenResponse)
def register(user: UserCreate):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Username taken")
    hashed = pwd_context.hash(user.password)
    users_db[user.username] = User(username=user.username, email=user.email, hashed_password=hashed)
    from auth import create_access_token
    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token, token_type="bearer")

@app.post("/auth/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_db.get(form_data.username)
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    from auth import create_access_token
    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token, token_type="bearer")

@app.get("/protected")
def protected(token: str = Depends(oauth2_scheme)):
    try:
        from auth import SECRET_KEY, ALGORITHM
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"user": payload.get("sub"), "status": "authenticated"}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/")
def root():
    return {"msg": "Auth service running", "endpoints": ["/auth/register", "/auth/login", "/protected"]}
```

3. models.py:
```python
from pydantic import BaseModel
class User(BaseModel):
    username: str
    email: str
    hashed_password: str
class Token(BaseModel):
    access_token: str
    token_type: str
```

4. schemas.py:
```python
from pydantic import BaseModel, EmailStr
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
class TokenResponse(BaseModel):
    access_token: str
    token_type: str
```

5. auth.py:
```python
import jwt
from datetime import datetime, timedelta
from typing import Optional

SECRET_KEY = "benchmark-secret-key"
ALGORITHM = "HS256"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
```

After writing all files, run: pip install -q -r requirements.txt && python -c "from main import app; print('FastAPI auth service loaded OK')"
''',        }),
        type('Task', (), {
            'id': 'python_package',
            'name': 'Python Multi-File Package',
            'difficulty': 'medium',
            'prompt': '''Create a Python package at /tmp/benchmark_workspace/mypackage/

Create the following files with proper relative imports:

1. mypackage/__init__.py - exports Animal, Dog, Cat classes
2. mypackage/animals.py - Base Animal class with name and speak() method (raises NotImplementedError)
3. mypackage/dogs.py - Dog extends Animal, returns "woof"
4. mypackage/cats.py - Cat extends Animal, returns "meow"
5. mypackage/main.py - Creates Dog and Cat instances and prints their sounds

After writing all files, run: cd /tmp/benchmark_workspace && python -c "from mypackage import Dog, Cat; d = Dog('Buddy'); c = Cat('Whiskers'); print(d.speak(), c.speak())"
''',        }),
        type('Task', (), {
            'id': 'git_script',
            'name': 'Git Workflow Automation Script',
            'difficulty': 'medium',
            'prompt': '''Write a bash script at /tmp/benchmark_workspace/gitflow.sh that:

1. ./gitflow.sh init - Initialize git repo if not exists, create .gitignore
2. ./gitflow.sh start <branch> - Create and switch to new branch
3. ./gitflow.sh commit <message> - Stage all and commit with message
4. ./gitflow.sh status - Show current branch and changed files
5. ./gitflow.sh finish - Merge current branch to main/master and delete it

Use colored output (green/red/yellow). Handle errors gracefully.

After writing, run: chmod +x /tmp/benchmark_workspace/gitflow.sh && /tmp/benchmark_workspace/gitflow.sh --help
''',        }),
        type('Task', (), {
            'id': 'react_components',
            'name': 'React TypeScript Component Library',
            'difficulty': 'hard',
            'prompt': '''Create a React component library at /tmp/benchmark_workspace/ui-components/

Create these 5 TypeScript React 18 components with FULL TypeScript types:

1. Button.tsx - variant (primary|secondary|ghost|danger), size (sm|md|lg), children, onClick, disabled, type
2. Card.tsx - title, description, children, footer slot
3. Modal.tsx - isOpen, onClose, title, children, size (sm|md|lg), with ESC key handling
4. Input.tsx - label, type, placeholder, value, onChange, error message
5. Select.tsx - label, options array [{value, label}], value, onChange, placeholder

Export each component. Use React.FC with proper generic types.

After writing, verify each file exists.
''',        }),
        type('Task', (), {
            'id': 'self_correct_loop',
            'name': 'Self-Correction Write-Verify-Fix',
            'difficulty': 'hard',
            'prompt': '''Write a Python file at /tmp/benchmark_workspace/self_correct/stats.py with INTENTIONAL bugs:

1. Define calculate_stats(numbers) that returns (sum, average)
2. Put a TYPO BUG: use 'number' instead of 'numbers' in the sum call
3. Put a SYNTAX BUG: missing colon after function definition
4. Run: python /tmp/benchmark_workspace/self_correct/stats.py - it MUST fail
5. Fix the bugs and run again until it prints: (15, 3.0)

The correct code should be:
def calculate_stats(numbers):
    total = sum(numbers)
    average = total / len(numbers)
    return (total, average)

result = calculate_stats([1, 2, 3, 4, 5])
print(result)

Report: what errors appeared, how many fix iterations, final output.
''',        }),
        type('Task', (), {
            'id': 'async_fastapi',
            'name': 'Async FastAPI with Database',
            'difficulty': 'hard',
            'prompt': '''Create an async FastAPI application at /tmp/benchmark_workspace/async_api/

1. requirements.txt:
fastapi==0.115.0
uvicorn[standard]==0.30.0
aiosqlite==0.20.0
sqlalchemy[asyncio]==2.0.35

2. database.py - async SQLite with aiosqlite, create_async_engine, AsyncSessionLocal, init_db, get_db
3. models.py - SQLAlchemy Item model (id, name, description, created_at), __tablename__="items"
4. schemas.py - Pydantic ItemCreate and ItemResponse schemas
5. main.py - FastAPI app with async /items GET, /items POST, /items/{id} GET, async lifespan

After writing, run: pip install -q -r requirements.txt && python -c "from main import app; print('async OK')"
''',        }),
        type('Task', (), {
            'id': 'debug_and_fix',
            'name': 'Debug and Fix Broken Python',
            'difficulty': 'medium',
            'prompt': '''Read /tmp/benchmark_workspace/buggy_app/app.py which has multiple bugs.
First create the buggy file:
```python
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route("/api/users/<id>")
def get_user(id):
    include_deets = request.args.get("include_details", default="false")
    if include_deets = "true"  # BUG: should be ==
        return jsonify({"error": "not implemented"}), 501
    return jsonify({"id": id, "name": "Test User"})

@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json()
    email = data["email"]  # BUG: might not exist
    return jsonify({"id": 1, "email": email}), 201

if __name__ == "__main__":
    app.run()
```

Then identify ALL bugs (syntax, logic, KeyError), fix them, and verify by running: pip install -q flask && python /tmp/benchmark_workspace/buggy_app/app.py
''',        }),
        type('Task', (), {
            'id': 'docker_script',
            'name': 'Docker Compose Full Stack App',
            'difficulty': 'extreme',
            'prompt': '''Create a Docker Compose full-stack application at /tmp/benchmark_workspace/fullstack/

Structure:
- docker-compose.yml with backend, frontend, and postgres services
- backend/ with Dockerfile, requirements.txt, main.py (FastAPI)
- frontend/ with Dockerfile, package.json, src/index.js, public/index.html

backend main.py should have /health endpoint and /users POST endpoint.
frontend should be React that calls the backend API.

After writing all files, list the complete directory structure.
''',        }),
    ]

    print("=" * 70)
    print("DRAGUNITEUS BENCHMARK - Streaming Code Quality Analysis")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    all_results = []

    for i, task in enumerate(TASKS):
        print(f"\n[{i+1}/{len(TASKS)}] {task.name} ({task.difficulty})")
        print("-" * 50)

        result = run_task(task.prompt, task_def_timeout := 300)

        quality = score_code_quality(result["text"], task.id)

        print(f"  Time: {result['elapsed']:.1f}s")
        print(f"  Quality Score: {quality['quality_score']}/100")
        print(f"  Text length: {len(result['text'])} chars")

        if result.get("error"):
            print(f"  Error: {result['error'][:100]}")

        all_results.append({
            "task_id": task.id,
            "task_name": task.name,
            "difficulty": task.difficulty,
            "draguniteus_score": quality["quality_score"],
            "draguniteus_time": round(result["elapsed"], 1),
            "draguniteus_text_len": len(result["text"]),
            "draguniteus_error": result.get("error"),
            "quality_details": quality["details"],
        })

    # Summary
    total = sum(r["draguniteus_score"] for r in all_results)
    avg = total / len(all_results) if all_results else 0

    print(f"\n{'=' * 70}")
    print("DRAGUNITEUS RESULTS")
    print(f"{'=' * 70}")
    print(f"Average Quality Score: {avg:.1f}/100")
    print()
    for r in sorted(all_results, key=lambda x: -x["draguniteus_score"]):
        print(f"  {r['task_name']:<35} {r['draguniteus_score']:>6.1f}/100  {r['draguniteus_time']:>6.1f}s")

    # Save
    output_file = Path("C:/tmp/draguniteus_benchmark_results.json")
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "model": "MiniMax-M2.7",
            "results": all_results,
            "summary": {
                "average_score": round(avg, 1),
                "total": len(all_results),
                "total_time": sum(r["draguniteus_time"] for r in all_results),
            }
        }, f, indent=2)

    print(f"\nSaved to: {output_file}")
    return all_results


if __name__ == "__main__":
    run_benchmark()
