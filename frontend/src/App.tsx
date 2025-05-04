import { useState } from "react";
import reactLogo from "./assets/react.svg";
import viteLogo from "/vite.svg";

function App() {
  const [count, setCount] = useState(0);

  return (
    /* Full‑screen flex container to prove Tailwind is active */
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-100">
        <h1 className="text-5xl font-bold text-pink-500 underline bg-slate-200 p-4 rounded">
  Tailwind is officially working 🎉
</h1>


      {/* Logo row */}
      <div className="flex gap-6">
        <a href="https://vite.dev" target="_blank">
          <img src={viteLogo} className="logo" alt="Vite logo" />
        </a>
        <a href="https://react.dev" target="_blank">
          <img src={reactLogo} className="logo react" alt="React logo" />
        </a>
      </div>

      {/* Heading */}
      <h1 className="text-red-500 text-2xl p-4">Vite + React</h1>

      {/* Counter card */}
      <div className="card">
        <button onClick={() => setCount((c) => c + 1)}>count is {count}</button>
        <p>
          Edit <code>src/App.tsx</code> and save to test HMR
        </p>
      </div>

      {/* Footer */}
      <p className="read-the-docs">
        Click on the Vite and React logos to learn more
      </p>
    </div>
  );
}

export default App;
