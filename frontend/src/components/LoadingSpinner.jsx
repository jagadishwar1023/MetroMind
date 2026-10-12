import { Loader2 } from 'lucide-react';

export default function LoadingSpinner() {
  return (
    <div className="flex justify-center items-center p-8 w-full h-full">
      <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
    </div>
  );
}
