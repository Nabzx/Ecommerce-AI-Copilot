import { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
}

export default function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`bg-[#14161A] rounded-xl border border-[#1F2937] shadow-lg ${className}`}>
      {children}
    </div>
  );
}

