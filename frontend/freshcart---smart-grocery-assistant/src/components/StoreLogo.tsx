import React from 'react';

interface StoreLogoProps {
  slug: string;
  name?: string;
  className?: string;
}

const StoreLogo: React.FC<StoreLogoProps> = ({ slug, name, className = "size-full" }) => {
  const s = slug?.toLowerCase() || '';

  // Definición de colores y estilos por marca
  const storeStyles: Record<string, { bg: string, icon: string, label: string }> = {
    'lider': { bg: 'bg-[#0071ce]', icon: 'text-[#ffc220]', label: 'L' },
    'jumbo': { bg: 'bg-[#00a650]', icon: 'text-white', label: 'J' },
    'santa-isabel': { bg: 'bg-[#e30613]', icon: 'text-white', label: 'S' },
    'unimarc': { bg: 'bg-[#da291c]', icon: 'text-white', label: 'U' },
  };

  const current = storeStyles[s] || { bg: 'bg-primary', icon: 'text-white', label: s.charAt(0).toUpperCase() };

  // SVG de Lider (Círculo azul con sol amarillo)
  if (s === 'lider') {
    return (
      <div className={`${className} ${current.bg} rounded-full flex items-center justify-center overflow-hidden p-0.5`}>
        <svg viewBox="0 0 24 24" fill="none" className="size-full">
          <circle cx="12" cy="12" r="10" fill="#0071ce" />
          <path d="M12 7V5M12 19v-2M7 12H5m14 0h-2m-2.464-4.536l-1.414-1.414M8.878 15.122l-1.414-1.414m10.606 0l-1.414 1.414M8.878 8.878L7.464 7.464" stroke="#ffc220" strokeWidth="2" strokeLinecap="round" />
          <circle cx="12" cy="12" r="3" fill="#ffc220" />
        </svg>
      </div>
    );
  }

  // SVG de Jumbo (Elefante verde estilizado o Círculo con J)
  if (s === 'jumbo') {
    return (
      <div className={`${className} ${current.bg} rounded-full flex items-center justify-center p-1`}>
        <span className="text-white font-black text-xs leading-none">J</span>
      </div>
    );
  }

  // SVG de Santa Isabel
  if (s === 'santa-isabel') {
    return (
      <div className={`${className} ${current.bg} rounded-full flex items-center justify-center p-1`}>
        <span className="text-white font-black text-xs leading-none">S</span>
      </div>
    );
  }

  // SVG de Unimarc
  if (s === 'unimarc') {
    return (
      <div className={`${className} ${current.bg} rounded-full flex items-center justify-center p-1`}>
        <span className="text-white font-black text-xs leading-none uppercase">U</span>
      </div>
    );
  }

  // Fallback genérico
  return (
    <div className={`${className} ${current.bg} rounded-full flex items-center justify-center shadow-inner`}>
      <span className={`font-bold ${current.icon} text-xs`}>{current.label}</span>
    </div>
  );
};

export default StoreLogo;
