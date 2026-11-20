"use client";

import dynamic from "next/dynamic";

const BuildingMap = dynamic(
  () => import("@/components/BuildingMap"),
  {
    ssr: false,
    loading: () => <p>Loading AI NETRA Map...</p>,
  }
);

export default function Home() {
  return (
    <main>
      <header
        style={{
          padding: "14px 20px",
          background: "#102a43",
          color: "white",
        }}
      >
        <h2>AI NETRA — Hyderabad Building Intelligence</h2>
        <p>Moosarambagh | Building-Level Flood Rescue Intelligence</p>
      </header>

      <BuildingMap />
    </main>
  );
}