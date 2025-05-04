# SpendLens

A personal finance tool that provides insights and analysis of financial transactions.

## Project Structure

```
spendlens/
├── frontend/          # React + TypeScript frontend
├── backend/           # FastAPI backend
│   ├── app/          # Main application code
│   ├── tests/        # Backend tests
│   └── requirements/ # Python dependencies
├── docs/             # Documentation
└── scripts/          # Development and deployment scripts
```

## Development Setup

### Prerequisites
- Node.js (v18 or later)
- Python (v3.9 or later)
- Git

### Backend Setup
1. Create and activate virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate  # Windows
   ```

2. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. Run the development server:
   ```bash
   uvicorn app.main:app --reload
   ```

### Frontend Setup
1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Run the development server:
   ```bash
   npm run dev
   ```

## Development Workflow

1. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit them:
   ```bash
   git add .
   git commit -m "Description of your changes"
   ```

3. Push your changes and create a pull request:
   ```bash
   git push origin feature/your-feature-name
   ```

## Contributing
Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License
This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details. 