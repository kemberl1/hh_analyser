import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

interface WidgetWrapperProps {
  title: string;
  description?: string;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  isEmpty?: boolean;
  lowConfidence?: boolean;
  onRetry?: () => void;
  children: ReactNode;
  className?: string;
}

export function WidgetWrapper({
  title,
  description,
  isLoading,
  isError,
  error,
  isEmpty,
  lowConfidence,
  onRetry,
  children,
  className,
}: WidgetWrapperProps) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              {title}
              {lowConfidence && (
                <Badge variant="warning">⚠ Мало данных</Badge>
              )}
            </CardTitle>
            {description && <CardDescription>{description}</CardDescription>}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-[200px] w-full" />
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <AlertCircle className="h-8 w-8 mb-2 text-destructive" />
            <p className="text-sm mb-2">
              {error?.message || "Ошибка загрузки данных"}
            </p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
              >
                <RefreshCw className="h-3 w-3" /> Повторить
              </button>
            )}
          </div>
        ) : isEmpty ? (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <p className="text-sm">Нет данных за выбранный период</p>
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}
