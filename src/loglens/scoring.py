from scipy.stats import poisson


def poisson_surprise(base_count, window_count, alpha=0.5):
    lam = base_count + alpha
    if window_count < lam:
        # fewer than expected → lower tail (VANISHED / drop)
        return -poisson.logcdf(window_count, mu=lam)
    # as many or more than expected → upper tail (NEW / SPIKE)
    return -poisson.logsf(window_count - 1, mu=lam)