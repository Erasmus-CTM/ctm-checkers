def test(check, symbols):
    def score(values, coverage=1):
        return check({"coverage": coverage, "regression": {"polynomialValues": values}}, symbols)["score"]
    assert score([i/5 for i in range(6)]) == 1
    assert score([(i/5)**2 for i in range(6)]) == 1
    assert score([0]*6) < 1
    assert score([-i/5 for i in range(6)]) < 1
    assert score([i/5 for i in range(6)], 0.5) < 1
    assert score([]) == 0
    # Old sampled secants all rise, but the derivative dips below -0.001.
    f = lambda x: 1000/3*(x-0.5025)**3 - 0.002*x
    assert min((f((i+1)/200)-f(i/200))*200 for i in range(200)) > 0
    assert score([f(i/5) for i in range(6)]) < 1
