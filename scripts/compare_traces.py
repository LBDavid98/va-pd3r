#!/usr/bin/env python
"""Compare token usage between two trace files."""
import json
import sys

def analyze_trace(path):
    """Extract intent classification stats from trace."""
    tokens = 0
    cost = 0
    calls = 0
    
    with open(path, 'r') as f:
        for line in f:
            data = json.loads(line)
            if data.get('node_name') == 'intent_classification_node':
                for call in data.get('llm_calls', []):
                    tokens += call.get('input_tokens', 0) + call.get('output_tokens', 0)
                    cost += call.get('cost_estimate', 0)
                    calls += 1
    
    return calls, tokens, cost

if __name__ == "__main__":
    old_path = "output/logs/20260121_194130_e7d6b708.jsonl"
    new_path = "output/logs/20260121_203015_84583c39.jsonl"
    
    old_calls, old_tokens, old_cost = analyze_trace(old_path)
    new_calls, new_tokens, new_cost = analyze_trace(new_path)
    
    print("=" * 50)
    print("Intent Classification Comparison")
    print("=" * 50)
    print(f"\nOLD (baseline):")
    print(f"  Calls:          {old_calls}")
    print(f"  Tokens:         {old_tokens:,}")
    print(f"  Cost:           ${old_cost:.4f}")
    print(f"  Avg tokens/call: {old_tokens/old_calls:.0f}")
    
    print(f"\nNEW (optimized):")
    print(f"  Calls:          {new_calls}")
    print(f"  Tokens:         {new_tokens:,}")
    print(f"  Cost:           ${new_cost:.4f}")
    print(f"  Avg tokens/call: {new_tokens/new_calls:.0f}")
    
    print(f"\nSAVINGS:")
    print(f"  Token reduction: {(1 - new_tokens/old_tokens)*100:.1f}%")
    print(f"  Cost reduction:  {(1 - new_cost/old_cost)*100:.1f}%")
    print("=" * 50)
