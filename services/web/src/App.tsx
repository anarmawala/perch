import { useState } from "preact/hooks";
import { useHashRoute } from "@/lib/hooks";
import { TopBar } from "@/components/TopBar";
import { SpeciesModal, type SpeciesTarget } from "@/components/SpeciesModal";
import { Live } from "@/views/Live";
import { Timeline } from "@/views/Timeline";
import { Settings } from "@/views/Settings";

export function App() {
  const [route, navigate] = useHashRoute();
  const [target, setTarget] = useState<SpeciesTarget | null>(null);

  const openSpecies = (species: string, extra?: Partial<SpeciesTarget>) => {
    if (!species || species === "Bird") return;
    setTarget({ species, ...extra });
  };

  return (
    <div class="flex h-full flex-col">
      <TopBar route={route} navigate={navigate} />
      <main class="min-h-0 flex-1">
        {route === "live" && <Live openSpecies={openSpecies} />}
        {route === "timeline" && <Timeline openSpecies={openSpecies} />}
        {route === "settings" && <Settings />}
      </main>
      {target && <SpeciesModal target={target} onClose={() => setTarget(null)} />}
    </div>
  );
}
