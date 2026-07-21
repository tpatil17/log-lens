from scipy.stats import poisson

def poisson_surprise(base_count, window_count, alpha=0.5):
    lam = base_count + alpha
    # sf(k-1) = P(X >= k); logsf stays in log-space, no underflow
    return -poisson.logsf(window_count - 1, mu=lam)

