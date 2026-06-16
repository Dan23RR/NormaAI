import { useState, useCallback, useRef, useEffect } from 'react';

/**
 * Citation event from SSE stream.
 */
export interface CitationEvent {
  type: 'citation';
  celex: string;
  urn: string | null;
  article: string;
  title: string;
  url: string;
  verified: boolean;
}

/**
 * Verification start event from SSE stream.
 */
export interface VerificationStartEvent {
  type: 'verification_start';
  claim: string;
  claim_index: number;
  total_claims: number;
}

/**
 * Verification result event from SSE stream.
 */
export interface VerificationResultEvent {
  type: 'verification_result';
  claim: string;
  claim_index: number;
  verified: boolean;
  confidence: number;
  evidence: string;
}

/**
 * Phase change event from SSE stream.
 */
export interface PhaseChangeEvent {
  type: 'phase_change';
  phase: string;
  message: string;
}

/**
 * Token event from SSE stream (incremental text).
 */
export interface TokenEvent {
  type: 'token';
  content: string;
  index: number;
}

/**
 * Error event from SSE stream.
 */
export interface ErrorEvent {
  type: 'error';
  message: string;
  recoverable: boolean;
}

/**
 * Done event with final statistics.
 */
export interface DoneStats {
  total_tokens: number;
  confidence_score: number;
  requires_review: boolean;
  cove_applied: boolean;
}

export interface DoneEvent {
  type: 'done';
  total_tokens: number;
  confidence_score: number;
  requires_review: boolean;
  cove_applied: boolean;
}

/**
 * Union of all possible SSE event types.
 */
export type SSEEvent =
  | TokenEvent
  | CitationEvent
  | VerificationStartEvent
  | VerificationResultEvent
  | PhaseChangeEvent
  | ErrorEvent
  | DoneEvent;

/**
 * Callback options for useSSEStream hook.
 */
export interface UseSSEStreamOptions {
  /**
   * Called when a token event is received.
   */
  onToken?: (content: string, index: number) => void;

  /**
   * Called when a citation event is received.
   */
  onCitation?: (citation: CitationEvent) => void;

  /**
   * Called when verification starts for a claim.
   */
  onVerificationStart?: (claim: string, index: number, total: number) => void;

  /**
   * Called when a verification result is received.
   */
  onVerificationResult?: (claim: string, verified: boolean, confidence: number, evidence: string) => void;

  /**
   * Called when the phase changes (draft → planning → verification → revision → validation).
   */
  onPhaseChange?: (phase: string, message: string) => void;

  /**
   * Called when an error event is received.
   */
  onError?: (message: string, recoverable: boolean) => void;

  /**
   * Called when the stream completes (done event).
   */
  onDone?: (stats: DoneStats) => void;

  /**
   * Enable automatic reconnection on transient errors.
   * Defaults to true.
   */
  autoReconnect?: boolean;

  /**
   * Maximum number of reconnection attempts.
   * Defaults to 3.
   */
  maxRetries?: number;

  /**
   * Delay in milliseconds before retrying.
   * Defaults to 1000.
   */
  retryDelay?: number;
}

/**
 * React hook for consuming SSE streams from intelligence endpoints.
 *
 * Handles:
 * - Streaming events (tokens, citations, verifications, phase changes)
 * - Error handling with optional auto-reconnect
 * - Proper cleanup on unmount
 * - Accumulated state (tokens, citations, current phase, etc.)
 *
 * @example
 * ```tsx
 * const { startStream, tokens, isStreaming, error } = useSSEStream({
 *   onToken: (content) => console.log(content),
 *   onPhaseChange: (phase, msg) => console.log(`${phase}: ${msg}`),
 * });
 *
 * // Start streaming
 * await startStream('/api/v1/qa/stream', { question: '...' }, authToken);
 *
 * // Stop streaming
 * stopStream();
 * ```
 */
export function useSSEStream(options: UseSSEStreamOptions = {}) {
  const {
    onToken,
    onCitation,
    onVerificationStart,
    onVerificationResult,
    onPhaseChange,
    onError,
    onDone,
    autoReconnect = true,
    maxRetries = 3,
    retryDelay = 1000,
  } = options;

  // State
  const [isStreaming, setIsStreaming] = useState(false);
  const [tokens, setTokens] = useState<string[]>([]);
  const [citations, setCitations] = useState<CitationEvent[]>([]);
  const [verifications, setVerifications] = useState<VerificationResultEvent[]>([]);
  const [currentPhase, setCurrentPhase] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<DoneStats | null>(null);

  // Refs for tracking abort and retry state
  const abortControllerRef = useRef<AbortController | null>(null);
  const retryCountRef = useRef(0);

  /**
   * Parse a single SSE event line.
   * Format: `data: {json}\n\n`
   */
  const parseSSEEvent = (line: string): SSEEvent | null => {
    if (!line.startsWith('data: ')) return null;
    if (line === 'data: [DONE]') return null;
    if (line.startsWith(': keepalive')) return null; // Keepalive comment

    try {
      const jsonStr = line.slice('data: '.length);
      return JSON.parse(jsonStr) as SSEEvent;
    } catch (e) {
      console.warn('Failed to parse SSE event:', line, e);
      return null;
    }
  };

  /**
   * Process a single SSE event and dispatch to appropriate callback.
   */
  const handleEvent = (event: SSEEvent) => {
    switch (event.type) {
      case 'token':
        setTokens((prev) => [...prev, event.content]);
        onToken?.(event.content, event.index);
        break;

      case 'citation':
        setCitations((prev) => [...prev, event]);
        onCitation?.(event);
        break;

      case 'verification_start':
        onVerificationStart?.(event.claim, event.claim_index, event.total_claims);
        break;

      case 'verification_result':
        setVerifications((prev) => [...prev, event]);
        onVerificationResult?.(event.claim, event.verified, event.confidence, event.evidence);
        break;

      case 'phase_change':
        setCurrentPhase(event.phase);
        onPhaseChange?.(event.phase, event.message);
        break;

      case 'error':
        setError(event.message);
        onError?.(event.message, event.recoverable);
        break;

      case 'done':
        const doneStats: DoneStats = {
          total_tokens: event.total_tokens,
          confidence_score: event.confidence_score,
          requires_review: event.requires_review,
          cove_applied: event.cove_applied,
        };
        setStats(doneStats);
        onDone?.(doneStats);
        break;
    }
  };

  /**
   * Stream response body using fetch with ReadableStream.
   * Parses SSE format line-by-line.
   */
  const streamResponse = async (response: Response) => {
    const reader = response.body?.getReader();
    if (!reader) throw new Error('Response body is not readable');

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true });

        // Split by double newlines (SSE format)
        const lines = buffer.split('\n\n');

        // Keep the last incomplete line in buffer
        buffer = lines.pop() || '';

        // Process complete lines
        for (const line of lines) {
          const trimmedLine = line.trim();
          if (trimmedLine) {
            const event = parseSSEEvent(trimmedLine);
            if (event) {
              handleEvent(event);
            }
          }
        }
      }

      // Process any remaining buffer
      if (buffer.trim()) {
        const event = parseSSEEvent(buffer.trim());
        if (event) {
          handleEvent(event);
        }
      }
    } finally {
      reader.releaseLock();
    }
  };

  /**
   * Start streaming from the given URL with POST body and auth token.
   */
  const startStream = useCallback(
    async (url: string, body: object, authToken: string) => {
      // Clean up any existing stream
      stopStream();

      // Reset state
      setIsStreaming(true);
      setTokens([]);
      setCitations([]);
      setVerifications([]);
      setCurrentPhase('');
      setError(null);
      setStats(null);
      retryCountRef.current = 0;

      // Create abort controller for this stream
      abortControllerRef.current = new AbortController();

      const attemptStream = async () => {
        try {
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${authToken}`,
            },
            body: JSON.stringify(body),
            signal: abortControllerRef.current?.signal,
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }

          await streamResponse(response);
          setIsStreaming(false);
        } catch (err) {
          // Don't treat abort as an error
          if (err instanceof Error && err.name === 'AbortError') {
            setIsStreaming(false);
            return;
          }

          const errorMsg = err instanceof Error ? err.message : 'Unknown error';

          // Attempt reconnection for transient errors
          if (autoReconnect && retryCountRef.current < maxRetries) {
            retryCountRef.current++;
            setError(`Connection lost. Reconnecting... (attempt ${retryCountRef.current}/${maxRetries})`);
            await new Promise((resolve) => setTimeout(resolve, retryDelay));
            await attemptStream();
          } else {
            setError(errorMsg);
            onError?.(errorMsg, retryCountRef.current < maxRetries);
            setIsStreaming(false);
          }
        }
      };

      await attemptStream();
    },
    [autoReconnect, maxRetries, retryDelay, onError]
  );

  /**
   * Stop the current stream.
   */
  const stopStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  /**
   * Reset all state.
   */
  const reset = useCallback(() => {
    stopStream();
    setTokens([]);
    setCitations([]);
    setVerifications([]);
    setCurrentPhase('');
    setError(null);
    setStats(null);
  }, [stopStream]);

  /**
   * Clean up on unmount.
   */
  useEffect(() => {
    return () => {
      stopStream();
    };
  }, [stopStream]);

  return {
    isStreaming,
    tokens,
    citations,
    verifications,
    currentPhase,
    error,
    stats,
    startStream,
    stopStream,
    reset,
  };
}
