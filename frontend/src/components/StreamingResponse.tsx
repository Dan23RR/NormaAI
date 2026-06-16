'use client';

import React, { useEffect, useState, useMemo } from 'react';
import {
  CheckCircle,
  AlertCircle,
  Clock,
  Zap,
  ExternalLink,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useSSEStream, CitationEvent, VerificationResultEvent } from '@/hooks/useSSEStream';

/**
 * Props for the StreamingResponse component.
 */
interface StreamingResponseProps {
  /**
   * The API endpoint URL (e.g., '/api/v1/qa/stream').
   */
  endpoint: string;

  /**
   * The request payload to send.
   */
  payload: object;

  /**
   * Authentication token.
   */
  authToken: string;

  /**
   * Callback when streaming completes successfully.
   */
  onComplete?: () => void;

  /**
   * Callback when streaming encounters an error.
   */
  onError?: (error: string) => void;

  /**
   * Optional class name for the container.
   */
  className?: string;
}

/**
 * Typing animation effect for streaming text.
 */
const TypingCursor: React.FC<{ visible: boolean }> = ({ visible }) => {
  if (!visible) return null;
  return (
    <span className="inline-block w-1 h-5 ml-1 bg-blue-500 animate-pulse rounded-sm" />
  );
};

/**
 * Renders a single citation with metadata and verification badge.
 */
const CitationBadge: React.FC<{ citation: CitationEvent; index: number }> = ({ citation, index }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      key={`citation-${index}`}
      className="mb-3 p-3 bg-slate-50 border border-slate-200 rounded-md hover:bg-slate-100 transition"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono bg-blue-100 text-blue-700 px-2 py-1 rounded">
              {citation.celex || citation.urn || 'Reference'}
            </span>
            {citation.verified && (
              <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded flex items-center gap-1">
                <CheckCircle className="w-3 h-3" />
                Verified
              </span>
            )}
            {!citation.verified && (
              <span className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                Unverified
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-slate-900 mb-1">{citation.title}</p>
          <p className="text-xs text-slate-600">{citation.article}</p>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-1 hover:bg-slate-200 rounded transition"
          aria-label="Toggle citation details"
        >
          {expanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </button>
      </div>

      {expanded && citation.url && (
        <div className="mt-2 pt-2 border-t border-slate-200">
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1"
          >
            View full document
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      )}
    </div>
  );
};

/**
 * Renders verification progress and results.
 */
const VerificationPanel: React.FC<{
  verifications: VerificationResultEvent[];
  currentPhase: string;
  isStreaming: boolean;
}> = ({ verifications, currentPhase, isStreaming }) => {
  if (verifications.length === 0 && currentPhase !== 'verification') {
    return null;
  }

  const verified = verifications.filter((v) => v.verified).length;
  const total = verifications.length;
  const avgConfidence = total > 0
    ? (verifications.reduce((sum, v) => sum + v.confidence, 0) / total * 100).toFixed(0)
    : 0;

  return (
    <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
      <h3 className="text-sm font-semibold text-blue-900 mb-3 flex items-center gap-2">
        <Sparkles className="w-4 h-4" />
        Verification Results
      </h3>

      {currentPhase === 'verification' && isStreaming && (
        <div className="mb-3 text-xs text-blue-700 flex items-center gap-1">
          <Clock className="w-3 h-3 animate-spin" />
          Verifying claims...
        </div>
      )}

      {total > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-blue-800">
              {verified} of {total} claims verified
            </span>
            <span className="font-semibold text-blue-900">{avgConfidence}% avg confidence</span>
          </div>

          <div className="w-full bg-blue-200 rounded-full h-2">
            <div
              className="bg-green-500 h-2 rounded-full transition-all"
              style={{ width: `${total > 0 ? (verified / total) * 100 : 0}%` }}
            />
          </div>

          <div className="mt-3 space-y-2">
            {verifications.map((v, idx) => (
              <div
                key={`verification-${idx}`}
                className="text-xs p-2 bg-white rounded border border-blue-100"
              >
                <div className="flex items-start gap-2">
                  {v.verified ? (
                    <CheckCircle className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1">
                    <p className="text-blue-900 font-medium">{v.claim}</p>
                    <p className="text-slate-600 mt-1">{v.evidence}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-slate-500">
                        Confidence: {(v.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * Phase indicator showing workflow progress.
 */
const PhaseIndicator: React.FC<{ phase: string; isStreaming: boolean }> = ({
  phase,
  isStreaming,
}) => {
  const phases = ['draft', 'planning', 'verification', 'revision', 'validation'];
  const currentIndex = phases.indexOf(phase);

  return (
    <div className="mb-4 flex items-center justify-between gap-2">
      {phases.map((p, idx) => (
        <React.Fragment key={p}>
          <div
            className={`flex items-center justify-center w-8 h-8 rounded-full text-xs font-semibold transition ${
              idx <= currentIndex
                ? 'bg-blue-600 text-white'
                : 'bg-slate-200 text-slate-600'
            } ${idx === currentIndex && isStreaming ? 'animate-pulse' : ''}`}
          >
            {idx + 1}
          </div>
          {idx < phases.length - 1 && (
            <div
              className={`flex-1 h-1 transition ${
                idx < currentIndex ? 'bg-blue-600' : 'bg-slate-200'
              }`}
            />
          )}
        </React.Fragment>
      ))}
    </div>
  );
};

/**
 * StreamingResponse component.
 *
 * Renders a real-time streaming response with:
 * - Accumulated text with typing animation
 * - Phase progress indicator
 * - Citations with verification badges
 * - Verification progress and results
 * - Confidence score and review warnings
 * - Error handling and retry
 */
export const StreamingResponse: React.FC<StreamingResponseProps> = ({
  endpoint,
  payload,
  authToken,
  onComplete,
  onError,
  className = '',
}) => {
  const [hasStarted, setHasStarted] = useState(false);

  const {
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
  } = useSSEStream({
    onPhaseChange: () => {
      // Phase changes handled by state updates
    },
    onError: (message) => {
      onError?.(message);
    },
    onDone: () => {
      onComplete?.();
    },
  });

  // Start streaming on mount
  useEffect(() => {
    if (!hasStarted) {
      setHasStarted(true);
      startStream(endpoint, payload, authToken).catch((err) => {
        console.error('Failed to start stream:', err);
        onError?.(err instanceof Error ? err.message : 'Failed to start streaming');
      });
    }

    return () => {
      // Note: We don't stop the stream here, only on explicit user action
    };
  }, [hasStarted, endpoint, payload, authToken, startStream, onError]);

  // Accumulate tokens into final text
  const accumulatedText = useMemo(() => tokens.join(''), [tokens]);

  if (error && !isStreaming) {
    return (
      <div className={`p-4 bg-red-50 border border-red-200 rounded-lg ${className}`}>
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="font-semibold text-red-900 mb-1">Streaming Error</h3>
            <p className="text-sm text-red-800 mb-3">{error}</p>
            <button
              onClick={() => {
                reset();
                setHasStarted(false);
              }}
              className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Phase indicator */}
      {currentPhase && <PhaseIndicator phase={currentPhase} isStreaming={isStreaming} />}

      {/* Main response text */}
      {accumulatedText && (
        <div className="p-4 bg-white border border-slate-200 rounded-lg">
          <div className="prose prose-sm max-w-none text-slate-900 leading-relaxed">
            <p>{accumulatedText}</p>
            <TypingCursor visible={isStreaming} />
          </div>
        </div>
      )}

      {/* Loading state */}
      {isStreaming && !accumulatedText && (
        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" />
          <span className="text-sm text-slate-600">Generating response...</span>
        </div>
      )}

      {/* Citations panel */}
      {citations.length > 0 && (
        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2">
            <Zap className="w-4 h-4" />
            Citations ({citations.length})
          </h3>
          <div className="space-y-2">
            {citations.map((citation, idx) => (
              <CitationBadge key={idx} citation={citation} index={idx} />
            ))}
          </div>
        </div>
      )}

      {/* Verification panel */}
      {verifications.length > 0 && (
        <VerificationPanel
          verifications={verifications}
          currentPhase={currentPhase}
          isStreaming={isStreaming}
        />
      )}

      {/* Stats and metadata */}
      {stats && (
        <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
          <div className="grid grid-cols-2 gap-4 mb-3">
            <div>
              <p className="text-xs text-green-600 uppercase font-semibold">Confidence Score</p>
              <p className="text-2xl font-bold text-green-900">
                {(stats.confidence_score * 100).toFixed(0)}%
              </p>
            </div>
            <div>
              <p className="text-xs text-green-600 uppercase font-semibold">Tokens Generated</p>
              <p className="text-2xl font-bold text-green-900">{stats.total_tokens}</p>
            </div>
          </div>

          {stats.requires_review && (
            <div className="flex items-start gap-2 p-2 bg-amber-100 border border-amber-300 rounded text-xs text-amber-900">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>This response requires expert review before use.</span>
            </div>
          )}

          {stats.cove_applied && (
            <div className="flex items-start gap-2 p-2 bg-blue-100 border border-blue-300 rounded text-xs text-blue-900">
              <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>Chain-of-Verification (CoVe) anti-hallucination pipeline applied.</span>
            </div>
          )}
        </div>
      )}

      {/* Stop button for active streams */}
      {isStreaming && (
        <div className="flex justify-center">
          <button
            onClick={stopStream}
            className="px-4 py-2 bg-slate-200 text-slate-900 text-sm rounded hover:bg-slate-300 transition"
          >
            Stop Streaming
          </button>
        </div>
      )}
    </div>
  );
};

export default StreamingResponse;
