# ML System Optimization — Programming Assignment 2 (Group 69)

## Topic
Parallel BoW TF-IDF + Cosine Similarity Retrieval (Top-K Merge) on Sentiment140.

## Code
Notebook: BITS/MLSysOpt/Group69_Assignment2.ipynb

## How to Run
1. Open the notebook in Google Colab.
2. Run cells top-to-bottom (dataset download is handled in the notebook).
3. Key outputs:
   - Serial baseline runtime T(1)
   - Parallel runtimes T(2) (naive and optimized)
   - Median-of-repeats table and runtime/speedup plots

## Performance Metrics
- Runtime: T(p)
- Speedup: S(p) = T(1)/T(p)
- Efficiency: E(p) = S(p)/p

## Dataset
Sentiment140 (Stanford): trainingandtestdata.zip
