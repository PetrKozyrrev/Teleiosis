import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';

export function useSourceReturn() {
  const [prompt, setPrompt] = useState(false);
  const current = useRef<{ left: boolean; returned: boolean; opened: boolean } | null>(null);

  const showIfReturned = useCallback(() => {
    if (current.current?.opened && current.current.returned) {
      current.current = null;
      setPrompt(true);
    }
  }, []);

  useEffect(() => {
    const leave = () => { if (current.current) current.current.left = true; };
    const resume = () => {
      if (current.current?.left) current.current.returned = true;
      showIfReturned();
    };
    const state = AppState.addEventListener('change', next => { if (next === 'active') resume(); else leave(); });
    const blur = AppState.addEventListener('blur', leave);
    const focus = AppState.addEventListener('focus', resume);
    return () => { state.remove(); blur.remove(); focus.remove(); };
  }, [showIfReturned]);

  const dismiss = useCallback(() => {
    current.current = null;
    setPrompt(false);
  }, []);

  function start() {
    dismiss();
    const attempt = { left: false, returned: false, opened: false };
    current.current = attempt;
    return (opened: boolean, returned = false) => {
      if (current.current !== attempt) return;
      if (!opened) { current.current = null; return; }
      attempt.opened = true;
      attempt.returned ||= returned;
      showIfReturned();
    };
  }
  return { prompt, start, dismiss };
}
