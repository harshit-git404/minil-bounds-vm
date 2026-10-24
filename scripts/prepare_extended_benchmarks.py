#!/usr/bin/env python3
"""
Task 9: Extended MiniL Benchmarks.
Generates 10 additional benchmarks in benchmarks/:
1. qsort.minil (data-dependent)
2. msort.minil (statically provable)
3. poly_gemm.minil (statically provable)
4. lu.minil (statically provable)
5. jacobi1d.minil (statically provable)
6. jacobi2d.minil (statically provable)
7. fir.minil (statically provable)
8. hash_table.minil (data-dependent)
9. knapsack.minil (statically provable)
10. lcs.minil (statically provable)
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BENCHMARKS = {
    "qsort.minil": """// Quick sort (data-dependent)
int data[20000];

int partition(int low, int high) {
    int pivot = data[high];
    int i = low - 1;
    int j = low;
    int temp = 0;
    while (j < high) {
        if (data[j] <= pivot) {
            i = i + 1;
            temp = data[i];
            data[i] = data[j];
            data[j] = temp;
        }
        j = j + 1;
    }
    int temp2 = data[i + 1];
    data[i + 1] = data[high];
    data[high] = temp2;
    return i + 1;
}

int qsort(int low, int high) {
    if (low < high) {
        int pi = partition(low, high);
        qsort(low, pi - 1);
        qsort(pi + 1, high);
    }
    return 0;
}

int main() {
    int n = 15000;
    int seed = 1234567;
    int i = 0;
    while (i < n) {
        seed = (seed * 1103515245 + 12345) % 2147483647;
        if (seed < 0) {
            seed = -seed;
        }
        data[i] = seed % 100000;
        i = i + 1;
    }
    qsort(0, n - 1);

    int chk = 0;
    i = 0;
    while (i < n) {
        chk = (chk * 31 + data[i]) % 1000000007;
        i = i + 1;
    }
    print(chk);
    return 0;
}
""",

    "msort.minil": """// Merge sort (statically provable / parameter-bounded)
int data[20000];
int temp[20000];

int merge(int l, int m, int r) {
    int i = l;
    int j = m + 1;
    int k = l;
    while (k <= r) {
        temp[k] = data[k];
        k = k + 1;
    }
    k = l;
    while (i <= m) {
        if (j <= r) {
            if (temp[i] <= temp[j]) {
                data[k] = temp[i];
                i = i + 1;
            } else {
                data[k] = temp[j];
                j = j + 1;
            }
        } else {
            data[k] = temp[i];
            i = i + 1;
        }
        k = k + 1;
    }
    while (j <= r) {
        data[k] = temp[j];
        j = j + 1;
        k = k + 1;
    }
    return 0;
}

int msort(int l, int r) {
    if (l < r) {
        int m = (l + r) / 2;
        msort(l, m);
        msort(m + 1, r);
        merge(l, m, r);
    }
    return 0;
}

int main() {
    int n = 15000;
    int seed = 9876543;
    int i = 0;
    while (i < n) {
        seed = (seed * 1103515245 + 12345) % 2147483647;
        if (seed < 0) {
            seed = -seed;
        }
        data[i] = seed % 100000;
        i = i + 1;
    }
    msort(0, n - 1);

    int chk = 0;
    i = 0;
    while (i < n) {
        chk = (chk * 31 + data[i]) % 1000000007;
        i = i + 1;
    }
    print(chk);
    return 0;
}
""",

    "poly_gemm.minil": """// PolyBench-style GEMM (statically provable)
int a[6400];
int b[6400];
int c[6400];

int main() {
    int n = 80;
    int alpha = 2;
    int beta = 3;
    int i = 0;
    int j = 0;
    int k = 0;
    int idx = 0;

    while (i < 80) {
        j = 0;
        while (j < 80) {
            idx = i * 80 + j;
            a[idx] = (i * j + 1) % 100;
            b[idx] = (i - j + 100) % 100;
            c[idx] = (i + j) % 50;
            j = j + 1;
        }
        i = i + 1;
    }

    i = 0;
    while (i < 80) {
        j = 0;
        while (j < 80) {
            idx = i * 80 + j;
            c[idx] = c[idx] * beta;
            k = 0;
            while (k < 80) {
                c[idx] = c[idx] + alpha * a[i * 80 + k] * b[k * 80 + j];
                k = k + 1;
            }
            j = j + 1;
        }
        i = i + 1;
    }

    int chk = 0;
    i = 0;
    while (i < 6400) {
        chk = (chk * 17 + c[i]) % 1000000007;
        i = i + 1;
    }
    print(chk);
    return 0;
}
""",

    "lu.minil": """// LU decomposition without pivoting (statically provable)
int a[10000];
int l[10000];
int u[10000];

int main() {
    int n = 100;
    int i = 0;
    int j = 0;
    int k = 0;
    int idx = 0;
    int sum = 0;
    int denom = 0;

    while (i < 100) {
        j = 0;
        while (j < 100) {
            idx = i * 100 + j;
            if (i == j) {
                a[idx] = 1000 + i;
            } else {
                a[idx] = ((i + 1) * (j + 1)) % 100 + 1;
            }
            l[idx] = 0;
            u[idx] = 0;
            j = j + 1;
        }
        i = i + 1;
    }

    i = 0;
    while (i < 100) {
        k = i;
        while (k < 100) {
            sum = 0;
            j = 0;
            while (j < i) {
                sum = sum + l[i * 100 + j] * u[j * 100 + k];
                j = j + 1;
            }
            u[i * 100 + k] = a[i * 100 + k] - sum;
            k = k + 1;
        }

        k = i + 1;
        while (k < 100) {
            sum = 0;
            j = 0;
            while (j < i) {
                sum = sum + l[k * 100 + j] * u[j * 100 + i];
                j = j + 1;
            }
            denom = u[i * 100 + i];
            if (denom != 0) {
                l[k * 100 + i] = (a[k * 100 + i] - sum) / denom;
            }
            k = k + 1;
        }
        l[i * 100 + i] = 1;
        i = i + 1;
    }

    int chk = 0;
    i = 0;
    while (i < 10000) {
        chk = (chk * 31 + l[i] + u[i]) % 1000000007;
        i = i + 1;
    }
    print(chk);
    return 0;
}
""",

    "jacobi1d.minil": """// Jacobi 1D 3-point stencil (statically provable)
int a[40000];
int b[40000];

int main() {
    int n = 40000;
    int t_steps = 10;
    int i = 0;
    int t = 0;

    while (i < 40000) {
        a[i] = (i * 37 + 11) % 1000;
        b[i] = 0;
        i = i + 1;
    }

    while (t < 10) {
        i = 1;
        while (i < 39999) {
            b[i] = (a[i - 1] + a[i] + a[i + 1]) / 3;
            i = i + 1;
        }
        i = 1;
        while (i < 39999) {
            a[i] = (b[i - 1] + b[i] + b[i + 1]) / 3;
            i = i + 1;
        }
        t = t + 1;
    }

    int chk = 0;
    i = 0;
    while (i < 40000) {
        chk = (chk * 19 + a[i]) % 1000000007;
        i = i + 1;
    }
    print(chk);
    return 0;
}
""",

    "jacobi2d.minil": """// Jacobi 2D 5-point stencil (statically provable)
int a[14400];
int b[14400];

int main() {
    int n = 120;
    int t_steps = 10;
    int i = 0;
    int j = 0;
    int t = 0;
    int idx = 0;

    while (i < 14400) {
        a[i] = (i * 43 + 7) % 1000;
        b[i] = 0;
        i = i + 1;
    }

    while (t < 10) {
        i = 1;
        while (i < 119) {
            j = 1;
            while (j < 119) {
                idx = i * 120 + j;
                b[idx] = (a[idx - 120] + a[idx + 120] + a[idx - 1] + a[idx + 1] + a[idx]) / 5;
                j = j + 1;
            }
            i = i + 1;
        }
        i = 1;
        while (i < 119) {
            j = 1;
            while (j < 119) {
                idx = i * 120 + j;
                a[idx] = (b[idx - 120] + b[idx + 120] + b[idx - 1] + b[idx + 1] + b[idx]) / 5;
                j = j + 1;
            }
            i = i + 1;
        }
        t = t + 1;
    }

    int chk = 0;
    i = 0;
    while (i < 14400) {
        chk = (chk * 23 + a[i]) % 1000000007;
        i = i + 1;
    }
    print(chk);
    return 0;
}
""",

    "fir.minil": """// Finite Impulse Response filter (statically provable)
int x[30000];
int h[32];
int y[30000];

int main() {
    int n = 30000;
    int k = 0;
    int i = 0;
    int tap = 0;
    int acc = 0;

    while (k < 32) {
        h[k] = (k * 3 + 1) % 10;
        k = k + 1;
    }

    while (i < 30000) {
        x[i] = (i * 7 + 13) % 256;
        y[i] = 0;
        i = i + 1;
    }

    i = 32;
    while (i < 30000) {
        acc = 0;
        tap = 0;
        while (tap < 32) {
            acc = acc + h[tap] * x[i - tap];
            tap = tap + 1;
        }
        y[i] = acc % 1000000007;
        i = i + 1;
    }

    int chk = 0;
    i = 0;
    while (i < 30000) {
        chk = (chk * 29 + y[i]) % 1000000007;
        i = i + 1;
    }
    print(chk);
    return 0;
}
""",

    "hash_table.minil": """// Hash table with linear probing (data-dependent)
int table_key[65536];
int table_val[65536];
int queries[30000];

int main() {
    int cap = 65536;
    int mask = 65535;
    int num_keys = 25000;
    int i = 0;
    int seed = 54321;
    int k = 0;
    int v = 0;
    int slot = 0;
    int q = 0;
    int target = 0;

    while (i < 65536) {
        table_key[i] = 0;
        table_val[i] = 0;
        i = i + 1;
    }

    i = 0;
    while (i < 25000) {
        seed = (seed * 1103515245 + 12345) % 2147483647;
        if (seed < 0) {
            seed = -seed;
        }
        k = seed % 1000000 + 1;
        v = (k * 31 + 7) % 50000;
        slot = k % 65536;
        while (table_key[slot] != 0) {
            slot = (slot + 1) % 65536;
        }
        table_key[slot] = k;
        table_val[slot] = v;
        queries[i] = k;
        i = i + 1;
    }

    int chk = 0;
    while (q < 50000) {
        target = queries[q % 25000];
        slot = target % 65536;
        while (table_key[slot] != target) {
            slot = (slot + 1) % 65536;
        }
        chk = (chk * 13 + table_val[slot]) % 1000000007;
        q = q + 1;
    }
    print(chk);
    return 0;
}
""",

    "knapsack.minil": """// 0/1 Knapsack dynamic programming (statically provable)
int weights[150];
int values[150];
int dp[3001];

int main() {
    int n = 150;
    int cap = 3000;
    int i = 0;
    int w = 0;
    int wt = 0;
    int val = 0;
    int cand = 0;

    while (i < 150) {
        weights[i] = (i * 7 + 3) % 40 + 1;
        values[i] = (i * 13 + 5) % 100 + 1;
        i = i + 1;
    }

    while (w <= 3000) {
        dp[w] = 0;
        w = w + 1;
    }

    i = 0;
    while (i < 150) {
        wt = weights[i];
        val = values[i];
        w = 3000;
        while (w >= wt) {
            cand = dp[w - wt] + val;
            if (cand > dp[w]) {
                dp[w] = cand;
            }
            w = w - 1;
        }
        i = i + 1;
    }

    int chk = 0;
    w = 0;
    while (w <= 3000) {
        chk = (chk * 31 + dp[w]) % 1000000007;
        w = w + 1;
    }
    print(chk);
    return 0;
}
""",

    "lcs.minil": """// Longest Common Subsequence dynamic programming (statically provable)
int seq1[700];
int seq2[700];
int dp0[701];
int dp1[701];

int main() {
    int len = 700;
    int i = 0;
    int j = 0;
    int k = 0;
    int m1 = 0;
    int m2 = 0;

    while (i < 700) {
        seq1[i] = (i * 17 + 5) % 26;
        seq2[i] = (i * 23 + 9) % 26;
        i = i + 1;
    }

    while (j <= 700) {
        dp0[j] = 0;
        dp1[j] = 0;
        j = j + 1;
    }

    i = 0;
    while (i < 700) {
        j = 0;
        while (j < 700) {
            if (seq1[i] == seq2[j]) {
                dp1[j + 1] = dp0[j] + 1;
            } else {
                m1 = dp0[j + 1];
                m2 = dp1[j];
                if (m1 > m2) {
                    dp1[j + 1] = m1;
                } else {
                    dp1[j + 1] = m2;
                }
            }
            j = j + 1;
        }
        k = 0;
        while (k <= 700) {
            dp0[k] = dp1[k];
            k = k + 1;
        }
        i = i + 1;
    }

    int chk = dp0[700];
    print(chk);
    return 0;
}
"""
}

def generate_benchmarks():
    out_dir = os.path.join(REPO_ROOT, "benchmarks")
    for fname, code in BENCHMARKS.items():
        path = os.path.join(out_dir, fname)
        with open(path, "w") as f:
            f.write(code)
        print(f"Wrote benchmark: {fname}")

if __name__ == "__main__":
    generate_benchmarks()
