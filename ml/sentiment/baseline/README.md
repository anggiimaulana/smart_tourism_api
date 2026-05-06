# ml/sentiment/baseline/

Folder ini untuk menyimpan model baseline ML dari Google Colab.

## File yang diperlukan

```
ml/sentiment/baseline/
├── naive_bayes.pkl
├── svm.pkl
└── decision_tree.pkl
```

## Cara mendapatkan model

1. Jalankan Cell 9 di `scripts/colab/sentiment_training.ipynb`
2. Model tersimpan ke Google Drive: `MyDrive/smart-tourism-ai/sentiment-baseline/`
3. Download dan letakkan `.pkl` di sini

## Format model

Setiap file `.pkl` adalah `sklearn.pipeline.Pipeline` berisi:
- `TfidfVectorizer` (bigram, max_features=10000)
- Classifier dengan dukungan `predict_proba()` (CalibratedClassifierCV untuk SVM)
