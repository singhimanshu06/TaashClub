from app.game.room import RoomManager


def test_home_room_is_stable_and_uses_game_defaults():
    manager = RoomManager()
    first = manager.get("home")
    second = manager.get_default()

    assert first is second
    assert first.code == "HOME"
    assert first.game_type == "twentyeight"
    assert first.num_players == 4
    assert first.options["deals"]
