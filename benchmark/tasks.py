"""
Benchmark Tasks for Draguniteus vs Claude Code
Each task is concrete, verifiable, and hard enough to separate the strong from the weak.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BenchmarkTask:
    id: str
    name: str
    difficulty: str  # easy, medium, hard, extreme
    prompt: str
    setup: str = ""
    verify_cmd: str = ""
    expected_files: list = None
    clean_cmd: str = ""

    def __post_init__(self):
        if self.expected_files is None:
            self.expected_files = []

    def get_workspace(self) -> Path:
        return Path(f"/tmp/benchmark_workspace/{self.id}")


TASKS = [


    BenchmarkTask(
        id="fastapi_auth",
        name="FastAPI Authentication Service",
        difficulty="hard",
        prompt="""Create a complete FastAPI authentication service.

Create these files in /tmp/benchmark_workspace/fastapi_auth/:

1. requirements.txt:
fastapi==0.115.0
uvicorn[standard]==0.30.0
pyjwt==2.9.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9

2. main.py:
```python
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
from typing import Optional
import sys
sys.path.insert(0, '.')
from models import User, Token
from schemas import UserCreate, UserResponse, TokenResponse

app = FastAPI(title="Auth Service")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
SECRET_KEY = "benchmark-secret-key-do-not-use-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

users_db = {}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/auth/register", response_model=TokenResponse)
def register(user: UserCreate):
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Username taken")
    hashed = pwd_context.hash(user.password)
    users_db[user.username] = User(username=user.username, email=user.email, hashed_password=hashed)
    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token, token_type="bearer")

@app.post("/auth/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users_db.get(form_data.username)
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.username})
    return TokenResponse(access_token=token, token_type="bearer")

@app.get("/protected")
def protected(token: str = Depends(oauth2_scheme)):
    try:
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
from typing import Optional

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
from typing import Optional

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    username: str
    email: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
```

After writing all files, run: cd /tmp/benchmark_workspace/fastapi_auth && pip install -q -r requirements.txt && python -c "from main import app; print('FastAPI auth service loaded OK')"
""",
        expected_files=["main.py", "models.py", "schemas.py", "requirements.txt"],
        verify_cmd="cd /tmp/benchmark_workspace/fastapi_auth && pip install -q -r requirements.txt 2>/dev/null && python -c 'from main import app; print(\"OK\")'",
        clean_cmd="rm -rf /tmp/benchmark_workspace/fastapi_auth",
    ),


    BenchmarkTask(
        id="python_package",
        name="Python Multi-File Package",
        difficulty="medium",
        prompt="""Create a Python package at /tmp/benchmark_workspace/mypackage/

Create the following files:

1. mypackage/__init__.py:
```python
from .animals import Animal
from .dogs import Dog
from .cats import Cat

__all__ = ['Animal', 'Dog', 'Cat']
```

2. mypackage/animals.py:
```python
class Animal:
    def __init__(self, name: str):
        self.name = name

    def speak(self) -> str:
        raise NotImplementedError
```

3. mypackage/dogs.py:
```python
from .animals import Animal

class Dog(Animal):
    def speak(self) -> str:
        return "woof"
```

4. mypackage/cats.py:
```python
from .animals import Animal

class Cat(Animal):
    def speak(self) -> str:
        return "meow"
```

5. mypackage/main.py:
```python
from . import Dog, Cat

if __name__ == "__main__":
    d = Dog("Buddy")
    c = Cat("Whiskers")
    print(f"{d.name} says: {d.speak()}")
    print(f"{c.name} says: {c.speak()}")
```

After writing, run: cd /tmp/benchmark_workspace && python -c "from mypackage import Dog, Cat; d = Dog('Buddy'); c = Cat('Whiskers'); print(d.speak(), c.speak())"
""",
        expected_files=["mypackage/__init__.py", "mypackage/animals.py", "mypackage/dogs.py", "mypackage/cats.py", "mypackage/main.py"],
        verify_cmd="cd /tmp/benchmark_workspace && python -c 'from mypackage import Dog, Cat; d = Dog(\"Buddy\"); c = Cat(\"Whiskers\"); print(d.speak(), c.speak())'",
        clean_cmd="rm -rf /tmp/benchmark_workspace/mypackage",
    ),


    BenchmarkTask(
        id="git_script",
        name="Git Workflow Automation Script",
        difficulty="medium",
        prompt="""Write a bash script at /tmp/benchmark_workspace/gitflow.sh that automates a complete git workflow.

The script must support these subcommands:

1. ./gitflow.sh init - Initialize git repo if not already, create .gitignore
2. ./gitflow.sh start <branch-name> - Create and switch to a new branch from main/master
3. ./gitflow.sh commit <message> - Stage all changes and commit with the message
4. ./gitflow.sh status - Show current branch and list of changed/new/deleted files
5. ./gitflow.sh finish - Merge current branch to main/master and delete the branch
6. ./gitflow.sh log --oneline - Show last 10 commits on current branch

Requirements:
- Use colored output (green for additions, red for deletions, yellow for changes)
- Handle errors gracefully (check if git repo exists, if branch already exists, etc.)
- Auto-detect main vs master as default branch
- Make the script executable

After writing, run: chmod +x /tmp/benchmark_workspace/gitflow.sh && /tmp/benchmark_workspace/gitflow.sh --help
""",
        expected_files=["gitflow.sh"],
        verify_cmd="chmod +x /tmp/benchmark_workspace/gitflow.sh && /tmp/benchmark_workspace/gitflow.sh --help",
        clean_cmd="rm -f /tmp/benchmark_workspace/gitflow.sh",
    ),


    BenchmarkTask(
        id="react_components",
        name="React TypeScript Component Library",
        difficulty="hard",
        prompt="""Create a TypeScript React component library at /tmp/benchmark_workspace/ui-components/

Create these 5 TypeScript React 18 components:

1. Button.tsx:
```tsx
import React from 'react';

interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: 'button' | 'submit' | 'reset';
  className?: string;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  children,
  onClick,
  disabled = false,
  type = 'button',
  className = '',
}) => {
  const baseStyles = 'rounded font-medium transition-colors focus:outline-none focus:ring-2';

  const variantStyles = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500',
    secondary: 'bg-gray-200 text-gray-900 hover:bg-gray-300 focus:ring-gray-400',
    ghost: 'bg-transparent hover:bg-gray-100 focus:ring-gray-300',
    danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  };

  const sizeStyles = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg',
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${disabled ? 'opacity-50 cursor-not-allowed' : ''} ${className}`}
    >
      {children}
    </button>
  );
};
```

2. Card.tsx:
```tsx
import React from 'react';

interface CardProps {
  title?: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export const Card: React.FC<CardProps> = ({
  title,
  description,
  children,
  footer,
  className = '',
}) => {
  return (
    <div className={`bg-white rounded-lg border border-gray-200 shadow-sm ${className}`}>
      {(title || description) && (
        <div className="px-4 py-3 border-b border-gray-100">
          {title && <h3 className="text-lg font-semibold text-gray-900">{title}</h3>}
          {description && <p className="mt-1 text-sm text-gray-500">{description}</p>}
        </div>
      )}
      {children && <div className="px-4 py-3">{children}</div>}
      {footer && <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 rounded-b-lg">{footer}</div>}
    </div>
  );
};
```

3. Modal.tsx:
```tsx
import React, { useEffect } from 'react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
}) => {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const sizeStyles = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-2xl',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className={`relative bg-white rounded-lg shadow-xl w-full mx-4 ${sizeStyles[size]}`}>
        {title && (
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <h2 className="text-lg font-semibold">{title}</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
          </div>
        )}
        <div className="px-4 py-3">{children}</div>
      </div>
    </div>
  );
};
```

4. Input.tsx:
```tsx
import React from 'react';

interface InputProps {
  label?: string;
  type?: 'text' | 'email' | 'password' | 'number' | 'search';
  placeholder?: string;
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  error?: string;
  disabled?: boolean;
  className?: string;
}

export const Input: React.FC<InputProps> = ({
  label,
  type = 'text',
  placeholder,
  value,
  onChange,
  error,
  disabled = false,
  className = '',
}) => {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      {label && <label className="text-sm font-medium text-gray-700">{label}</label>}
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        className={`px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
          error ? 'border-red-500 focus:ring-red-500' : 'border-gray-300 focus:ring-blue-500'
        } ${disabled ? 'bg-gray-100 cursor-not-allowed' : ''}`}
      />
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  );
};
```

5. Select.tsx:
```tsx
import React from 'react';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps {
  label?: string;
  options: SelectOption[];
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  error?: string;
  className?: string;
}

export const Select: React.FC<SelectProps> = ({
  label,
  options,
  value,
  onChange,
  placeholder = 'Select...',
  disabled = false,
  error,
  className = '',
}) => {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      {label && <label className="text-sm font-medium text-gray-700">{label}</label>}
      <select
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        disabled={disabled}
        className={`px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
          error ? 'border-red-500 focus:ring-red-500' : 'border-gray-300 focus:ring-blue-500'
        } ${disabled ? 'bg-gray-100 cursor-not-allowed' : ''}`}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  );
};
```

After writing all files, verify TypeScript syntax by checking each file exists with correct content.
""",
        expected_files=["Button.tsx", "Card.tsx", "Modal.tsx", "Input.tsx", "Select.tsx"],
        verify_cmd="ls /tmp/benchmark_workspace/ui-components/*.tsx | wc -l",
        clean_cmd="rm -rf /tmp/benchmark_workspace/ui-components",
    ),


    BenchmarkTask(
        id="self_correct_loop",
        name="Self-Correction Write→Verify→Fix",
        difficulty="hard",
        prompt="""This task tests self-correction ability. Write a Python file at /tmp/benchmark_workspace/self_correct/stats.py with INTENTIONAL bugs, then fix them.

1. First write the file WITH these bugs:
   - Function name typo: calculate_stats (correct) but inside uses 'number' instead of 'numbers'
   - Missing colon after function definition
   - Wrong variable name in average calculation

2. Run: python /tmp/benchmark_workspace/self_correct/stats.py
   It MUST fail the first time.

3. Fix the bugs based on the error output.

4. Run again until it succeeds and prints: (15, 3.0)

The final working code should be:
```python
def calculate_stats(numbers):
    total = sum(numbers)
    average = total / len(numbers)
    return (total, average)

result = calculate_stats([1, 2, 3, 4, 5])
print(result)
```

Report: how many iterations it took, what errors appeared, and the final output.
""",
        expected_files=["stats.py"],
        verify_cmd="python /tmp/benchmark_workspace/self_correct/stats.py",
        clean_cmd="rm -rf /tmp/benchmark_workspace/self_correct",
    ),


    BenchmarkTask(
        id="async_fastapi",
        name="Async FastAPI with Database",
        difficulty="hard",
        prompt="""Create an async FastAPI application at /tmp/benchmark_workspace/async_api/

1. requirements.txt:
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
aiosqlite==0.20.0
sqlalchemy[asyncio]==2.0.35
```

2. database.py:
```python
import aiosqlite
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

DATABASE_URL = "sqlite+aiosqlite:///./benchmark.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

3. models.py:
```python
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from database import Base

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

4. schemas.py:
```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
```

5. main.py:
```python
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from contextlib import asynccontextmanager
import sys
sys.path.insert(0, '.')
from database import init_db, get_db
from models import Item
from schemas import ItemCreate, ItemResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Async API", lifespan=lifespan)

@app.post("/items/", response_model=ItemResponse)
async def create_item(item: ItemCreate, db: AsyncSession = Depends(get_db)):
    db_item = Item(name=item.name, description=item.description)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

@app.get("/items/", response_model=list[ItemResponse])
async def list_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item))
    items = result.scalars().all()
    return items

@app.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/")
async def root():
    return {"msg": "Async FastAPI running", "endpoints": ["/items/", "/items/{id}"]}
```

After writing, run: cd /tmp/benchmark_workspace/async_api && pip install -q -r requirements.txt && python -c "from main import app; print('async OK')"
""",
        expected_files=["main.py", "database.py", "models.py", "schemas.py", "requirements.txt"],
        verify_cmd="cd /tmp/benchmark_workspace/async_api && pip install -q -r requirements.txt 2>/dev/null && python -c 'from main import app; print(\"async OK\")'",
        clean_cmd="rm -rf /tmp/benchmark_workspace/async_api",
    ),


    BenchmarkTask(
        id="debug_and_fix",
        name="Debug and Fix Broken Python",
        difficulty="medium",
        prompt="""Fix all bugs in /tmp/benchmark_workspace/buggy_app/app.py

The file contains a Python web app with multiple bugs. Read it, identify ALL bugs (syntax, logic, and runtime), fix them, and verify it runs.

First, create the buggy file:
```python
# BUGGY CODE - DO NOT COPY THIS, READ FROM FILE
# Create the file with intentional bugs first

# Write buggy app.py:
with open('/tmp/benchmark_workspace/buggy_app/app.py', 'w') as f:
    f.write('''
from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# Bug 1: route has syntax error (missing colon)
@app.route("/api/users/<id>")
def get_user(id):
    # Bug 2: request.args.get with wrong key
    include_deets = request.args.get("include_details", default="false")
    # Bug 3: == vs = in condition
    if include_deets = "true"
        return jsonify({"error": "not implemented"}), 501
    # Bug 4: wrong variable name
    return jsonify({"id": id, "name": "Test User"})

# Bug 5: route with wrong decorator
@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json()
    # Bug 6: key might not exist
    email = data["email"]  # No KeyError handling
    return jsonify({"id": 1, "email": email}), 201

# Bug 7: missing debug config
if __name__ == "__main__":
    app.run()
''')

os.makedirs("/tmp/benchmark_workspace/buggy_app", exist_ok=True)
```

Then read the file, fix all bugs, and verify by running: pip install -q flask && python /tmp/benchmark_workspace/buggy_app/app.py &
sleep 2
curl -s http://127.0.0.1:5000/api/users/1 | head -c 200
curl -s -X POST http://127.0.0.1:5000/api/users -H "Content-Type: application/json" -d '{"username":"test","email":"test@example.com"}' | head -c 200
pkill -f "python.*buggy_app"

After fixing, the app should respond correctly to both endpoints.
""",
        expected_files=["app.py"],
        verify_cmd="pip install -q flask 2>/dev/null && cd /tmp/benchmark_workspace/buggy_app && python app.py & sleep 2 && curl -s http://127.0.0.1:5000/api/users/1 && curl -s -X POST http://127.0.0.1:5000/api/users -H 'Content-Type: application/json' -d '{\"username\":\"test\",\"email\":\"test@example.com\"}' && pkill -f 'python.*buggy_app' || true",
        clean_cmd="rm -rf /tmp/benchmark_workspace/buggy_app && pkill -f 'python.*buggy_app' 2>/dev/null || true",
    ),


    BenchmarkTask(
        id="docker_script",
        name="Docker Compose Full Stack App",
        difficulty="extreme",
        prompt="""Create a Docker Compose full-stack application at /tmp/benchmark_workspace/fullstack/

Structure:
1. docker-compose.yml:
```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/appdb
      - SECRET_KEY=benchmark-secret-key
    depends_on:
      - db
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=appdb
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  pgdata:
```

2. backend/Dockerfile:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

3. backend/requirements.txt:
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
psycopg2-binary==2.9.9
sqlalchemy==2.0.35
pydantic==2.9.0
```

4. backend/main.py:
```python
from fastapi import FastAPI
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/appdb")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Backend API")

@app.get("/")
def root():
    return {"msg": "Backend API running", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/users/")
def create_user(name: str, email: str):
    db = SessionLocal()
    user = User(name=name, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return {"id": user.id, "name": user.name, "email": user.email}
```

5. frontend/Dockerfile:
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

6. frontend/package.json:
```json
{
  "name": "frontend",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-scripts": "5.0.1"
  },
  "scripts": {
    "start": "react-scripts start"
  }
}
```

7. frontend/src/index.js:
```javascript
import React from 'react';
import ReactDOM from 'react-dom/client';

function App() {
  const [health, setHealth] = React.useState(null);

  React.useEffect(() => {
    fetch('http://localhost:8000/health')
      .then(r => r.json())
      .then(d => setHealth(d));
  }, []);

  return (
    <div style={{ fontFamily: 'system-ui', padding: '2rem' }}>
      <h1>Fullstack Benchmark App</h1>
      <p>Backend: {health ? '✅ Connected' : '⏳ Connecting...'}</p>
      {health && <pre>{JSON.stringify(health, null, 2)}</pre>}
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
```

8. frontend/public/index.html:
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Benchmark App</title>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
  </body>
</html>
```

After writing all files, verify the structure is correct by listing them.
""",
        expected_files=["docker-compose.yml", "backend/Dockerfile", "backend/requirements.txt", "backend/main.py", "frontend/Dockerfile", "frontend/package.json", "frontend/src/index.js", "frontend/public/index.html"],
        verify_cmd="ls -la /tmp/benchmark_workspace/fullstack/ && ls /tmp/benchmark_workspace/fullstack/backend/ && ls /tmp/benchmark_workspace/fullstack/frontend/",
        clean_cmd="rm -rf /tmp/benchmark_workspace/fullstack",
    ),
]
