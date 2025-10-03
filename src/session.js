import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { nanoid } from 'nanoid';

const defaultSession = () => ({
  id: null,
  file: null,
  progress: 0,
  isRecovering: false,
  recoveryDone: false,
  results: [],
  tempOutputDir: null,
  selectedAnalysisFile: null,
  activeTab: 'basic',
  selectedFilesForDownload: [],
  selectedPath: '',
  saveFrames: false,
  slackVideoSrc: '',
  openGroups: {},
});

export const useSessionStore = create(
  persist(
    (set, get) => ({
      session: defaultSession(),

      startSession: (file) => {
        set({
          session: {
            ...defaultSession(),
            id: nanoid(8),
            file,
            isRecovering: true,
            progress: 0,
            recoveryDone: false,
          },
        });
      },

      patchSession: (patch) => {
        const cur = get().session;
        if (!cur?.id) return;
        set({ session: { ...cur, ...patch } });
      },

      resetSession: () => set({ session: defaultSession() }),
    }),
    { name: 'virex-session' }
  )
);
