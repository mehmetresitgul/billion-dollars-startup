import pytest
from pacifor.core.kill_switch import KillSwitch
from pacifor.core.exceptions import KillSwitchEngaged


@pytest.fixture
def ks():
    return KillSwitch()


async def test_initially_not_engaged(ks):
    assert not await ks.is_engaged()


async def test_engage_sets_flag(ks):
    await ks.engage(reason="test")
    assert await ks.is_engaged()


async def test_release_clears_flag(ks):
    await ks.engage()
    await ks.release()
    assert not await ks.is_engaged()


async def test_check_raises_when_engaged(ks):
    await ks.engage(reason="emergency")
    with pytest.raises(KillSwitchEngaged) as exc_info:
        await ks.check()
    assert "Kill switch" in str(exc_info.value)


async def test_check_passes_when_released(ks):
    await ks.engage()
    await ks.release()
    await ks.check()  # should not raise
