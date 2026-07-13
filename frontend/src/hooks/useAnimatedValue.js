import { useState, useEffect, useRef } from 'react';

export function useAnimatedValue(targetValue, duration = 800) {
  const [displayValue, setDisplayValue] = useState(targetValue);
  const animationRef = useRef(null);
  const startValueRef = useRef(targetValue);
  const startTimeRef = useRef(null);

  useEffect(() => {
    if (animationRef.current) cancelAnimationFrame(animationRef.current);
    startValueRef.current = displayValue;
    startTimeRef.current = performance.now();

    const animate = (currentTime) => {
      const elapsed = currentTime - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = startValueRef.current + (targetValue - startValueRef.current) * eased;
      setDisplayValue(current);
      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      }
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [targetValue, duration]);

  return displayValue;
}
