"""Two local users exercise the actual watchlist and alert HTTP handlers."""

from models import DataAlert, User, WatchlistItem
from routers import user_features


def test_other_users_objects_are_not_read_or_modified(client, db_session):
    one = User(email='one@example.invalid', password_hash='!fixture')
    two = User(email='two@example.invalid', password_hash='!fixture')
    db_session.add_all([one, two])
    db_session.flush()
    own = WatchlistItem(user_id=one.id, item_type='county', item_id='one', label='Own')
    other = WatchlistItem(user_id=two.id, item_type='county', item_id='two', label='Private')
    own_alert = DataAlert(user_id=one.id, alert_type='new_audit', title='Own')
    other_alert = DataAlert(user_id=two.id, alert_type='new_audit', title='Private')
    db_session.add_all([own, other, own_alert, other_alert])
    db_session.commit()
    client.app.dependency_overrides[user_features.get_current_user] = lambda: one

    response = client.get('/api/v1/user/watchlist')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()] == [own.id]
    assert response.headers['cache-control'] == 'no-store'
    response = client.get('/api/v1/user/alerts')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()] == [own_alert.id]
    assert client.delete(f'/api/v1/user/watchlist/{other.id}').status_code == 404
    assert client.patch(f'/api/v1/user/alerts/{other_alert.id}').status_code == 404
    assert client.post('/api/v1/user/alerts/read-all').status_code == 200
    db_session.expire_all()
    assert db_session.get(WatchlistItem, other.id) is not None
    assert db_session.get(DataAlert, own_alert.id).read is True
    assert db_session.get(DataAlert, other_alert.id).read is False
