from app.game.room import RoomManager


def test_home_room_is_stable_and_defaults_to_twenty_rounds():
    manager = RoomManager()
    first = manager.get("home")
    second = manager.get_default()

    assert first is second
    assert first.code == "HOME"
    assert first.game_type == "twentyeight"
    assert first.num_players == 4
    assert first.options["deals"] == "20"


def test_home_uses_twenty_rounds_after_reset_without_changing_private_defaults():
    manager = RoomManager()
    home = manager.get_default()
    private = manager.create_room("twentyeight", 4, {})
    for room in (home, private):
        for _ in range(4):
            room.add_bot()
        room.start_game(room.host_id)

    assert home.game.total_rounds == 20
    assert private.game.total_rounds == 10

    home.game.force_end()
    assert manager.reset_finished_home(0) is home
    assert manager.get_default().options["deals"] == "20"
