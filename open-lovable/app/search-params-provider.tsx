'use client';
import { useSearchParams } from 'next/navigation';
import { ReactNode } from 'react';

interface SearchParamsProviderProps {
  children: (searchParams: URLSearchParams) => ReactNode;
}

export function SearchParamsProvider({ children }: SearchParamsProviderProps) {
  const searchParams = useSearchParams();
  return <>{children(searchParams)}</>;
}
