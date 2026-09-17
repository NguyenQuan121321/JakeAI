import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  hasError?: boolean;
  leftAdornment?: React.ReactNode;
  rightAdornment?: React.ReactNode;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, hasError = false, leftAdornment, rightAdornment, ...props }, ref) => {
    if (leftAdornment || rightAdornment) {
      return (
        <div className="relative flex items-center w-full">
          {leftAdornment && (
            <div className="absolute left-3 flex items-center pointer-events-none text-muted-foreground">
              {leftAdornment}
            </div>
          )}
          <input
            type={type}
            className={cn(
              "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ring-offset-background",
              leftAdornment && "pl-9",
              rightAdornment && "pr-9",
              hasError && "border-destructive focus-visible:ring-destructive",
              className
            )}
            ref={ref}
            aria-invalid={hasError ? "true" : undefined}
            {...props}
          />
          {rightAdornment && (
            <div className="absolute right-3 flex items-center text-muted-foreground">
              {rightAdornment}
            </div>
          )}
        </div>
      );
    }

    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ring-offset-background",
          hasError && "border-destructive focus-visible:ring-destructive",
          className
        )}
        ref={ref}
        aria-invalid={hasError ? "true" : undefined}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
