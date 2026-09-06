// SPDX-License-Identifier: AGPL-3.0-or-later
import GroupsPage from './GroupsPage';
import type {Locale,User} from './types';
// Keep the application navigation contract while using the published /groups API.
export default function Groups({user,locale,onLogin,onSelect}:{user:User|null;locale:Locale;t:(key:string)=>string;onLogin:()=>void;onSelect:(id:string)=>void}) {
 return <GroupsPage key={user?.username||'anonymous'} user={user} locale={locale} onLogin={onLogin} onOpenPlace={onSelect}/>;
}
